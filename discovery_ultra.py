#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import re
import logging
from pathlib import Path
from typing import Set, List, Union

import requests
from bs4 import BeautifulSoup

# --- НАСТРОЙКИ ---
SOURCES_FILE = Path("sources/telegram_channels.json")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://html.duckduckgo.com/",
}

SHODAN_API_KEY = os.getenv("SHODAN_API_KEY")

GEMINI_SOURCES = [
    "gemini://proxylist.geekify.org/",
    "gemini://lists.shh.sh/proxies.txt",
]

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def load_current_sources() -> Set[str]:
    """Загрузка источников с поддержкой старого и нового форматов."""
    if not SOURCES_FILE.is_file():
        logging.warning(f"Файл {SOURCES_FILE} не найден. Будет создан новый.")
        return set()
    try:
        with SOURCES_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        
        extracted = set()
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    url = item.get("url")
                    if url: extracted.add(str(url).strip())
                elif isinstance(item, str):
                    extracted.add(item.strip())
        return extracted
    except Exception as exc:
        logging.error(f"Ошибка чтения базы: {exc}")
        return set()

def save_sources(sources: Set[str]) -> None:
    """Сохранение в чистый список строк (современный стандарт)."""
    try:
        SOURCES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with SOURCES_FILE.open("w", encoding="utf-8") as f:
            json.dump(sorted(list(sources)), f, indent=2, ensure_ascii=False)
        logging.info(f"База обновлена: {len(sources)} источников.")
    except Exception as exc:
        logging.error(f"Ошибка записи: {exc}")

def search_shodan(query: str = "port:443 hysteria2", limit: int = 100) -> Set[str]:
    """Поиск через Shodan API."""
    if not SHODAN_API_KEY:
        logging.warning("Пропуск Shodan: API ключ не задан.")
        return set()

    url = "https://api.shodan.io/shodan/host/search"
    params = {"key": SHODAN_API_KEY, "query": query, "limit": limit}
    try:
        resp = requests.get(url, params=params, timeout=25)
        resp.raise_for_status()
        data = resp.json()
        
        proxies = set()
        for host in data.get("matches", []):
            ip = host.get("ip_str")
            port = host.get("port")
            if ip and port:
                # Добавляем как потенциальный HTTP/HTTPS источник для проверки сканером
                proxies.add(f"http://{ip}:{port}")
        return proxies
    except Exception as exc:
        logging.error(f"Shodan API Error: {exc}")
        return set()

def fetch_gemini(url: str) -> Set[str]:
    """Парсинг Gemini через gmi.io."""
    clean_url = url.replace("gemini://", "")
    gateway = f"https://gmi.io/{clean_url}"
    try:
        resp = requests.get(gateway, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        # Ищем любые намеки на http/https ссылки на конфиги
        links = re.findall(r"https?://[^\s'\"<>]+", resp.text)
        return {l.strip() for l in links if "github" in l or "pastebin" in l}
    except Exception as exc:
        logging.debug(f"Gemini {url} недоступен: {exc}")
        return set()

def search_web(query: str) -> Set[str]:
    """Поиск в DuckDuckGo HTML."""
    search_url = "https://html.duckduckgo.com/html/"
    found = set()
    try:
        # Важно: DuckDuckGo ожидает форму с параметром 'q'
        resp = requests.post(search_url, data={"q": query}, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        for a in soup.select("a.result__a"):
            href = a.get("href")
            if not href: continue
            
            # Очистка ссылок от редиректов DDG (если есть)
            if "uddg=" in href:
                href = requests.utils.unquote(href.split("uddg=")[1].split("&")[0])

            if "github.com" in href:
                # Превращаем обычную ссылку гитхаба в RAW
                if "/blob/" in href:
                    href = href.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
                found.add(href.strip())
    except Exception as exc:
        logging.warning(f"Web-поиск '{query}' не удался: {exc}")
    return found

def main():
    # 1. Загрузка
    current = load_current_sources()
    logging.info(f"В базе уже есть {len(current)} источников.")

    discovered = set()

    # 2. Поиск в Web (GitHub Raw)
    queries = [
        "site:github.com 'hysteria2' extension:txt",
        "site:github.com 'tuic' extension:yaml",
        "raw.githubusercontent.com hysteria2 proxi"
    ]
    for q in queries:
        logging.info(f"Поиск в Web: {q}")
        discovered.update(search_web(q))

    # 3. Gemini
    for g_url in GEMINI_SOURCES:
        logging.info(f"Проверка Gemini: {g_url}")
        discovered.update(fetch_gemini(g_url))

    # 4. Shodan
    logging.info("Запрос к Shodan...")
    discovered.update(search_shodan("port:443 hysteria2", limit=50))
    discovered.update(search_shodan("port:8080 tuic", limit=50))

    # 5. Итоги
    new_ones = {u for u in discovered if u not in current and u.startswith("http")}
    
    if new_ones:
        logging.info(f"✨ Найдено {len(new_ones)} новых источников!")
        all_sources = current.union(new_ones)
        save_sources(all_sources)
    else:
        logging.info("🤷‍♂️ Новых источников не обнаружено.")

if __name__ == "__main__":
    main()
