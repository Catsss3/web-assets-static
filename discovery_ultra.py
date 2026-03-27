#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json, logging, os, re, random, time, requests
from pathlib import Path
from typing import Set, List
from urllib.parse import parse_qs, urlparse, unquote
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

# --- CONFIG ---
OUTPUT_FILE = Path("sources/telegram_channels.json")
SOURCE_MARKERS = [r"hysteria2://", r"tuic://", r"\\b(?:\\d{1,3}\\.){3}\\d{1,3}:\\d{2,5}\\b"]
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

session = requests.Session()
retries = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retries))

def get_headers():
    return {"User-Agent": random.choice(USER_AGENTS), "Referer": "https://www.google.com/"}

def clean_url(href):
    parsed = urlparse(href)
    if parsed.path == "/url":
        qs = parse_qs(parsed.query)
        if "q" in qs: return unquote(qs["q"][0])
    return href

def search(engine, query):
    urls = set()
    base = f"https://www.google.com/search?q={query}&hl=en" if engine=="google" else f"https://html.duckduckgo.com/html/?q={query}"
    try:
        r = session.get(base, headers=get_headers(), cookies={'CONSENT': 'YES+'}, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a"):
            h = clean_url(a.get("href", ""))
            if h.startswith("http") and not any(x in h for x in ["google", "duckduckgo"]):
                urls.add(h.split('#')[0])
    except: pass
    return urls

def is_valid(url):
    try:
        r = session.get(url, headers=get_headers(), timeout=10, stream=True)
        data = r.raw.read(300*1024, decode_content=True).decode('utf-8', errors='ignore')
        return any(re.search(m, data, re.IGNORECASE) for m in SOURCE_MARKERS)
    except: return False

def main():
    db = set()
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, "r") as f: db = set(json.load(f))
    
    found, checked = set(), set()
    
    # ИСПРАВЛЕННЫЙ СПИСОК ЗАПРОСОВ С ПРАВИЛЬНЫМИ ОТСТУПАМИ
    queries = [
        "site:t.me/s/ 'hysteria2://'",
        "site:t.me/s/ 'tuic://'",
        "site:github.com 'hysteria2://' extension:txt",
        "site:github.com 'tuic://' extension:txt",
        "site:gist.github.com 'hysteria2://'",
        "site:gist.github.com 'tuic://'",
        "site:pastebin.com 'hysteria2://'",
        "site:pastebin.com 'tuic://'",
        "intitle:'index of' 'hysteria2.txt'",
        "intitle:'index of' 'tuic.txt'",
        "'hysteria2' 'proxy' filetype:txt",
        "site:raw.githubusercontent.com 'tuic://'",
        "site:cdn.jsdelivr.net 'hysteria2://'"
    ]
    
    for q in queries:
        logging.info(f"🔎 Поиск: {q}")
        found.update(search("google", q))
        time.sleep(random.uniform(5, 10))
        found.update(search("ddg", q))

    new_src = set()
    for l in found:
        if l not in db and l not in checked:
            if is_valid(l):
                new_src.add(l)
                logging.info(f"✅ НАЙДЕН: {l}")
            else: checked.add(l)

    if new_src:
        final = sorted(list(db.union(new_src)))
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, "w") as f: json.dump(final, f, indent=2)
        logging.info(f"✨ Добавлено {len(new_src)} источников.")
    else: logging.info("😴 Ничего нового.")

if __name__ == '__main__': main()
