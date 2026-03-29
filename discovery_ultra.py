#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json, logging, os, re, random, time, requests
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------- НАСТРОЙКИ ----------
OUTPUT_FILE = Path("sources/telegram_channels.json")
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

# Старые маркеры контента
SOURCE_MARKERS = [
    r"hysteria2://",
    r"tuic://",
    r"\\b(?:\\d{1,3}\\.) {3}\\d{1,3}:\\d{2,5}\\b",
]
COMPILED_MARKERS = [re.compile(m, re.IGNORECASE) for m in SOURCE_MARKERS]

# НОВЫЕ маркеры для поиска ссылок-подписок (Subscription Links)
SUB_MARKERS = [
    r"/api/v1/client/subscribe\?token=",
    r"/sub\?target=",
    r"/subscribe\?token=",
    r"/link/[a-zA-Z0-9]{10,}",
]
COMPILED_SUB_MARKERS = [re.compile(m, re.IGNORECASE) for m in SUB_MARKERS]

# Твои старые запросы + НОВЫЕ для охоты на подписки
GOOGLE_QUERIES = [
    "site:t.me/s/ 'hysteria2://'",
    "site:t.me/s/ 'tuic://'",
    "site:telegram.me/s/ 'hysteria2://'",
    "site:cdn.jsdelivr.net 'hysteria2://'",
    "intitle:'index of' 'sub' 'hysteria2'", # Новое
    "site:pastebin.com 'hysteria2' 'subscribe?token='", # Новое
]
DUCK_QUERIES = [
    "hysteria2:// telegram",
    "tuic:// telegram",
    "hysteria2:// site:t.me",
    "hysteria2 sub link site:github.com", # Новое
]
REPO_QUERIES = ['hy2+extension:txt', 'tuic+extension:txt', 'sub+hysteria', 'subscribe+token+hy2']
GIST_QUERIES = ['hy2', 'tuic', 'subscribe+proxy']

# ---------- СЕССИЯ ----------
session = requests.Session()
retries = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retries))

def get_headers():
    return {"User-Agent": random.choice(USER_AGENTS), "Referer": "https://www.google.com/"}

def clean_url(href: str) -> str:
    parsed = urlparse(href)
    if parsed.path == "/url":
        qs = parse_qs(parsed.query)
        if "q" in qs: return unquote(qs["q"][0])
    return href

def is_valid(url: str) -> bool:
    # Если в самом URL уже есть признаки подписки - это VALID
    if any(p.search(url) for p in COMPILED_SUB_MARKERS):
        return True
    # Иначе проверяем контент (как раньше)
    try:
        r = session.get(url, headers=get_headers(), timeout=10, stream=True)
        chunk = r.raw.read(300 * 1024, decode_content=True).decode("utf-8", errors="ignore")
        return any(p.search(chunk) for p in COMPILED_MARKERS)
    except: return False

def validate_batch(urls: set) -> set:
    valid = set()
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(is_valid, u): u for u in urls}
        for f in as_completed(futures):
            if f.result(): valid.add(futures[f])
    return valid

def search_google(query: str) -> set:
    base = f"https://www.google.com/search?q={query}&hl=en"
    urls = set()
    try:
        r = session.get(base, headers=get_headers(), cookies={'CONSENT': 'YES+'}, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a"):
            href = clean_url(a.get("href", ""))
            if href.startswith("http") and not any(x in href for x in ("google", "duckduckgo")):
                urls.add(href.split('#')[0])
    except: pass
    return urls

def search_duckduckgo(query: str) -> set:
    base = f"https://html.duckduckgo.com/html/?q={query}"
    urls = set()
    try:
        r = session.get(base, headers=get_headers(), timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a.result__a"):
            href = a.get("href", "")
            if href.startswith("http"): urls.add(href.split('#')[0])
    except: pass
    return urls

def discover_github(token: str) -> set:
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    found = set()
    for q in REPO_QUERIES:
        try:
            url = f"https://api.github.com/search/code?q={q}&sort=indexed&order=desc"
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                for item in r.json().get('items', []):
                    raw = f"https://raw.githubusercontent.com/{item['repository']['full_name']}/main/{item['path']}"
                    if is_valid(raw): found.add(raw)
            time.sleep(2)
        except: pass
    for q in GIST_QUERIES:
        try:
            url = f"https://api.github.com/search/code?q={q}+host:gist.github.com&sort=indexed"
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                for item in r.json().get('items', []):
                    raw = item['html_url'].replace('/blob/', '/raw/')
                    if is_valid(raw): found.add(raw)
            time.sleep(2)
        except: pass
    return found

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    db = set()
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE) as f:
            try: db = set(json.load(f))
            except: pass
    
    new_src = set()
    token = os.getenv('GITHUB_TOKEN') or os.getenv('GithubApiToken')
    
    # 1. GitHub Search
    if token: new_src.update(discover_github(token))
    
    # 2. Google Search
    for q in GOOGLE_QUERIES:
        candidates = search_google(q) - db
        new_src.update(validate_batch(candidates))
        time.sleep(random.uniform(5, 10))
    
    # 3. DuckDuckGo Search
    for q in DUCK_QUERIES:
        candidates = search_duckduckgo(q) - db
        new_src.update(validate_batch(candidates))
        time.sleep(random.uniform(5, 10))
    
    if new_src:
        merged = sorted(db | new_src)
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, "w") as f: json.dump(merged, f, indent=2)
        logging.info(f"✨ Стелла добавила {len(new_src)} новых источников (включая подписки).")
    else:
        logging.info("😴 Новых элитных источников не найдено.")

if __name__ == "__main__":
    main()