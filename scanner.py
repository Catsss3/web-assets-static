
import json, re, os, requests, yaml, base64, logging
from concurrent.futures import ThreadPoolExecutor, as_completed

MAX_WORKERS = min(64, (os.cpu_count() or 1) * 8) 
TIMEOUT = 25
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
SOURCES_FILE = "sources/telegram_channels.json"
OUTPUT_FILE = "providers/hy2_list.txt"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

def decode_base64(data: str) -> str:
    try:
        cleaned = re.sub(r'[^a-zA-Z0-9+/=]', '', data.strip())
        missing = len(cleaned) % 4
        if missing: cleaned += "=" * (4 - missing)
        return base64.b64decode(cleaned).decode("utf-8", errors="ignore")
    except: return ""

def extract_links(text: str) -> list:
    proxy_pattern = r"(?:hy(?:steria)?2|tuic)://[a-zA-Z0-9%._~:-]+@[a-zA-Z0-9.-]+:[0-9]+[^\s#\"'<>]*"
    found = re.findall(proxy_pattern, text, flags=re.IGNORECASE)
    if len(found) < 2:
        potential_b64 = re.findall(r'[a-zA-Z0-9+/]{50,}=*', text)
        for chunk in potential_b64:
            decoded = decode_base64(chunk)
            if "://" in decoded: found.extend(re.findall(proxy_pattern, decoded, flags=re.IGNORECASE))
    return found

def parse_yaml_safe(text: str) -> list:
    links = []
    if 'proxies:' not in text.lower(): return links
    try:
        start_idx = text.lower().find('proxies:')
        data = yaml.safe_load(text[start_idx:])
        if not data or 'proxies' not in data: return links
        for p in data['proxies']:
            ptype = str(p.get('type', '')).lower()
            srv, prt = p.get('server'), p.get('port')
            if not srv or not prt: continue
            if ptype in ['hysteria2', 'hy2']:
                links.append(f"hysteria2://{p.get('auth', '')}@{srv}:{prt}?sni={p.get('sni', srv)}#{p.get('name', 'Hy2')}")
            elif ptype == 'tuic':
                auth = f"{p.get('uuid', '')}:{p.get('password', '')}" if p.get('password') else p.get('uuid', '')
                cong = p.get('congestion-control') or p.get('congestion_control') or 'bbr'
                links.append(f"tuic://{auth}@{srv}:{prt}?sni={p.get('sni', srv)}&alpn={','.join(p.get('alpn', ['h3']))}&congestion_control={cong}#{p.get('name', 'Tuic5')}")
    except: pass
    return links

def fetch_worker(url: str, depth=0) -> list:
    if "github.com" in url and "/blob/" in url:
        url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    try:
        r = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
        if r.status_code != 200: return []
        text = r.text
        found = extract_links(text)
        found.extend(parse_yaml_safe(text))
        
        # РЕКУРСИЯ: Если нашли ссылки на raw-файлы, заходим в них
        if depth == 0:
            sub_urls = re.findall(r'https?://(?:raw\.githubusercontent\.com|gist\.githubusercontent\.com|pastebin\.com)[^\s#\"''<>]+', text)
            if sub_urls:
                logging.info(f"  ↪️ Рекурсия: {len(sub_urls)} ссылок в {url}")
                with ThreadPoolExecutor(max_workers=10) as sub_ex:
                    futures = [sub_ex.submit(fetch_worker, s_url, depth=1) for s_url in sub_urls]
                    for f in as_completed(futures): found.extend(f.result())
        return found
    except: return []

def main():
    os.makedirs("providers", exist_ok=True)
    with open(SOURCES_FILE, "r") as f:
        src = json.load(f)
        urls = list(src.values()) if isinstance(src, dict) else src
    all_raw = set()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(fetch_worker, u) for u in urls]
        for f in as_completed(futures): all_raw.update(f.result())
    final = {}
    for link in all_raw:
        if link.lower().startswith("hy2://"): link = "hysteria2://" + link[6:]
        match = re.search(r'://([^/]+)@?([^/?#\s]+)', link)
        if match:
            key = f"{link.split(':')[0]}_{match.group(2)}"
            if key not in final: final[key] = link.strip()
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f: f.write("\n".join(final.values()))
    print(f"✅ Итог: {len(final)} уникальных прокси.")

if __name__ == '__main__':
    main()
