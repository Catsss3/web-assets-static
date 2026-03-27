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
SOURCE_MARKERS = [
    r"hysteria2://",
    r"tuic://",
    r"\\b(?:\\d{1,3}\\.) {3}\\d{1,3}:\\d{2,5}\\b",
]
COMPILED_MARKERS = [re.compile(m, re.IGNORECASE) for m in SOURCE_MARKERS]

GOOGLE_QUERIES = [
    "site:t.me/s/ 'hysteria2://'",
    "site:t.me/s/ 'tuic://'",
    "site:telegram.me/s/ 'hysteria2://'",
    "site:telegram.me/s/ 'tuic://'",
    "site:cdn.jsdelivr.net 'hysteria2://'",
]
DUCK_QUERIES = [
    "hysteria2:// telegram",
    "tuic:// telegram",
    "hysteria2:// site:t.me",
    "tuic:// site:t.me",
]
REPO_QUERIES = ['hy2+extension:txt', 'tuic+extension:txt', 'sub+hysteria']
GIST_QUERIES = ['hy2', 'tuic']

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
    if token: new_src.update(discover_github(token))
    for q in GOOGLE_QUERIES:
        candidates = search_google(q) - db
        new_src.update(validate_batch(candidates))
        time.sleep(random.uniform(5, 10))
    for q in DUCK_QUERIES:
        candidates = search_duckduckgo(q) - db
        new_src.update(validate_batch(candidates))
        time.sleep(random.uniform(5, 10))
    if new_src:
        merged = sorted(db | new_src)
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, "w") as f: json.dump(merged, f, indent=2)
        logging.info(f"✨ Добавлено {len(new_src)} новых источников.")
    else:
        logging.info("😴 Новых источников не найдено.")

if __name__ == "__main__":
    main()
