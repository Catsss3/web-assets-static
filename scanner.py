import json, re, os, requests, yaml, base64
from concurrent.futures import ThreadPoolExecutor

def decode_base64(data):
    try:
        missing_padding = len(data) % 4
        if missing_padding: data += '=' * (4 - missing_padding)
        return base64.b64decode(data).decode('utf-8', errors='ignore')
    except: return ""

def fetch_url(url):
    if 'github.com' in url and '/blob/' in url:
        url = url.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, timeout=30, headers=headers)
        if resp.status_code != 200: return []
        
        text = resp.text
        # Улучшенная регулярка: ищет и hy2:// и hysteria2://
        pattern = r"hy(?:steria)?2://[^\s#\"'<>]+"
        
        found = re.findall(pattern, text, flags=re.IGNORECASE)
        
        # Проверка Base64
        if not found or len(text.strip()) > 100:
            decoded = decode_base64(text.strip())
            if 'hy' in decoded.lower() and '2://' in decoded.lower():
                found.extend(re.findall(pattern, decoded, flags=re.IGNORECASE))

        # Парсинг YAML
        if 'proxies:' in text:
            try:
                y = yaml.safe_load(text)
                for p in y.get('proxies', []):
                    if p.get('type') in ['hysteria2', 'hy2']:
                        link = f"hysteria2://{p.get('auth')}@{p.get('server')}:{p.get('port')}?sni={p.get('sni', p.get('server',''))}#{p.get('name','')}"
                        found.append(link)
            except: pass
            
        return found
    except: return []

def clean_and_parse():
    print("📂 Загрузка источников...")
    try:
        with open('sources/telegram_channels.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            all_urls = list(data.values()) if isinstance(data, dict) else data
    except: return []

    print(f"📡 Глубокое сканирование (hy2 + hysteria2)...")
    raw_configs = set()
    
    with ThreadPoolExecutor(max_workers=50) as executor:
        for res in executor.map(fetch_url, all_urls):
            if res: raw_configs.update(res)

    unique_by_ip = {}
    for link in raw_configs:
        # Приводим всё к единому стандарту hysteria2:// для работы в приложениях
        if link.lower().startswith("hy2://"):
            link = "hysteria2://" + link[6:]
            
        clean = link.strip().rstrip('.,;)]}"')
        m = re.search(r'(?:@|^|//)([^:/@\s?#]+:[0-9]+)', clean)
        if m:
            ip_port = m.group(1)
            if ip_port not in unique_by_ip: unique_by_ip[ip_port] = clean

    return list(unique_by_ip.values())

if __name__ == '__main__':
    os.makedirs('providers', exist_ok=True)
    res = clean_and_parse()
    with open('providers/hy2_list.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(res))
    print(f"✅ Финальный итог: {len(res)} уникальных серверов.")