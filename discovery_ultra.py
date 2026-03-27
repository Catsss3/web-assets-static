#!/usr/bin/env python3
import json, logging, os, re, random, time, requests
from pathlib import Path
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

def is_valid(url):
    try:
        r = session.get(url, headers=get_headers(), timeout=10, stream=True)
        data = r.raw.read(300*1024, decode_content=True).decode('utf-8', errors='ignore')
        return any(re.search(m, data, re.IGNORECASE) for m in SOURCE_MARKERS)
    except: return False

def discover_from_github(token):
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    new_urls = set()
    
    # 1. Поиск по РЕПОЗИТОРИЯМ (твои новые ключи)
    repo_queries = ['hy2+extension:txt', 'tuic+extension:txt', 'sub+hysteria']
    for q in repo_queries:
        logging.info(f"🔎 GitHub Репозитории: {q}")
        try:
            url = f"https://api.github.com/search/code?q={q}&sort=indexed&order=desc"
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                for item in r.json().get('items', []):
                    raw_url = f"https://raw.githubusercontent.com/{item['repository']['full_name']}/main/{item['path']}"
                    if is_valid(raw_url): new_urls.add(raw_url)
            time.sleep(2)
        except: pass

    # 2. Поиск по ГИСТАМ (новое дополнение)
    gist_queries = ['hy2', 'tuic']
    for gq in gist_queries:
        logging.info(f"📝 GitHub Гисты: {gq}")
        try:
            url = f"https://api.github.com/search/code?q={gq}+host:gist.github.com&sort=indexed"
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                for item in r.json().get('items', []):
                    raw_url = item['html_url'].replace('/blob/', '/raw/')
                    if is_valid(raw_url): new_urls.add(raw_url)
            time.sleep(2)
        except: pass
        
    return new_urls

def search(engine, query):
    urls = set()
    base = f"https://www.google.com/search?q={query}&hl=en" if engine=="google" else f"https://html.duckduckgo.com/html/?q={query}"
    try:
        r = session.get(base, headers=get_headers(), cookies={'CONSENT': 'YES+'}, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a"):
            h = a.get("href", "")
            parsed = urlparse(h)
            if parsed.path == "/url":
                qs = parse_qs(parsed.query)
                if "q" in qs: h = unquote(qs["q"][0])
            if h.startswith("http") and not any(x in h for x in ["google", "duckduckgo"]):
                urls.add(h.split('#')[0])
    except: pass
    return urls

def main():
    db = set()
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, "r") as f:
            try: db = set(json.load(f))
            except: db = set()
    
    new_src = set()
    
    # 1. GitHub & Gist Discovery
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GithubApiToken')
    if token:
        github_sources = discover_from_github(token)
        new_src.update(github_sources)

    # 2. Search Engine Discovery (Твой Google поиск)
    google_queries = ["site:t.me/s/ 'hysteria2://'", "site:t.me/s/ 'tuic://'", "site:cdn.jsdelivr.net 'hysteria2://'"]
    for q in google_queries:
        logging.info(f"🔎 Google поиск: {q}")
        found = search("google", q)
        for l in found:
            if l not in db and is_valid(l): new_src.add(l)
        time.sleep(random.uniform(5, 10))

    if new_src:
        final = sorted(list(db.union(new_src)))
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, "w") as f: json.dump(final, f, indent=2)
        logging.info(f"✨ Готово! Добавлено {len(new_src)} новых источников.")
    else:
        logging.info("😴 Ничего нового не найдено.")

if __name__ == '__main__':
    main()
