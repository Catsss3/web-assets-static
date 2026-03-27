import json, re, os, requests, yaml, base64, logging, random
from concurrent.futures import ThreadPoolExecutor, as_completed

MAX_WORKERS = 64
TIMEOUT = 45
SOURCES_FILE = "sources/telegram_channels.json"
OUTPUT_FILE = "providers/hy2_list.txt"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

def decode_base64(data: str) -> str:
    try:
        cleaned = re.sub(r'\s+', '', data)
        missing = len(cleaned) % 4
        if missing: cleaned += "=" * (4 - missing)
        return base64.b64decode(cleaned).decode("utf-8", errors="ignore")
    except: return ""

def extract_links(text: str) -> list:
    proxy_pattern = r"(?:hy(?:steria)?2|tuic)://[^\s#\"'<>]+"
    found = re.findall(proxy_pattern, text, flags=re.IGNORECASE)
    if len(found) < 3:
        for chunk in re.findall(r'[A-Za-z0-9+/]{50,}=*', text):
            decoded = decode_base64(chunk)
            if "://" in decoded: found.extend(re.findall(proxy_pattern, decoded, flags=re.IGNORECASE))
    return found

def parse_yaml_safe(text: str) -> list:
    links = []
    text_lower = text.lower()
    keys = ['proxies:', 'proxy:', 'proxy-providers:']
    if not any(k in text_lower for k in keys): return links
    try:
        start = min(text_lower.find(k) for k in keys if k in text_lower)
        data = yaml.safe_load(text[start:])
        p_list = data.get('proxies') or data.get('proxy') or []
        for p in p_list:
            ptype = str(p.get('type', '')).lower()
            srv, prt = p.get('server'), p.get('port')
            if not srv or not prt: continue
            name = p.get('name', f"{ptype}_{srv}")
            if ptype in ['hysteria2', 'hy2']:
                links.append(f"hysteria2://{p.get('auth', '')}@{srv}:{prt}?sni={p.get('sni', srv)}#{name}")
            elif ptype == 'tuic':
                auth = f"{p.get('uuid', '')}:{p.get('password', '')}" if p.get('password') else p.get('uuid', '')
                cong = p.get('congestion-control') or p.get('congestion_control') or 'bbr'
                links.append(f"tuic://{auth}@{srv}:{prt}?sni={p.get('sni', srv)}&alpn={','.join(p.get('alpn', ['h3']))}&congestion_control={cong}#{name}")
    except: pass
    return links

def normalize_url(url: str) -> str:
    if "github.com" in url:
        if "/blob/" in url: return url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        if "/raw/" not in url and "raw.githubusercontent.com" not in url:
            parts = url.split("/")
            if len(parts) > 6: return f"https://raw.githubusercontent.com/{parts[3]}/{parts[4]}/{parts[6]}/{'/'.join(parts[7:])}"
    return url

def fetch_worker(url: str, depth=0) -> list:
    url = normalize_url(url)
    try:
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        r = requests.get(url, timeout=TIMEOUT, headers=headers, stream=True)
        if r.status_code != 200: return []
        content = r.raw.read(300 * 1024, decode_content=True).decode('utf-8', errors='ignore')
        found = extract_links(content)
        found.extend(parse_yaml_safe(content))
        if depth < 1:
            subs = re.findall(r'https?://(?:raw\.githubusercontent\.com|gist\.githubusercontent\.com|pastebin\.com)[^\s#\"''<>]+', content)
            if subs:
                with ThreadPoolExecutor(max_workers=5) as sub_ex:
                    futures = [sub_ex.submit(fetch_worker, u, depth+1) for u in subs]
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
        m = re.search(r'://([^@/]+)@?([^/?#\s]+)', link)
        if m:
            key = f"{link.split(':')[0]}_{m.group(2)}"
            if key not in final: final[key] = link.strip()
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f: f.write("\n".join(final.values()))
    logging.info(f"✅ Итог: {len(final)} уникальных прокси.")

if __name__ == '__main__': main()
