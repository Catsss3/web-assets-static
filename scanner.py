import json, re, os, requests, yaml
from concurrent.futures import ThreadPoolExecutor

# ГАРАНТИРОВАННЫЕ RAW-ССЫЛКИ (без посредников и HTML)
RAW_BASES = [
    "https://raw.githubusercontent.com/whoahaow/rjsxrd/main/githubmirror/split-by-protocols/hy2.txt",
    "https://raw.githubusercontent.com/whoahaow/rjsxrd/main/githubmirror/split-by-protocols/hy2-secure.txt",
    "https://raw.githubusercontent.com/whoahaow/rjsxrd/main/githubmirror/split-by-protocols/hysteria2.txt",
    "https://raw.githubusercontent.com/whoahaow/rjsxrd/main/githubmirror/split-by-protocols/hysteria2-secure.txt"
]

def fetch_url(url):
    try:
        # Принудительно меняем blob на raw, если ссылка ведет на страницу GitHub
        if 'github.com' in url and '/blob/' in url:
            url = url.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')
        
        resp = requests.get(url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
        if resp.status_code != 200: return []
        
        text = resp.text
        found = re.findall(r"hysteria2://[^\s#\"'<>]+", text, flags=re.IGNORECASE)
        
        # Парсим YAML если это конфиг
        if 'proxies:' in text:
            try:
                y = yaml.safe_load(text)
                for p in y.get('proxies', []):
                    if p.get('type') == 'hysteria2':
                        found.append(f"hysteria2://{p.get('auth')}@{p.get('server')}:{p.get('port')}?sni={p.get('sni','')}#{p.get('name','')}")
            except: pass
        
        # Если нашли мало, пробуем построчно
        if len(found) < 10:
            for line in text.splitlines():
                if 'hysteria2://' in line.lower(): found.append(line.strip())
        
        return found
    except: return []

def clean_and_parse():
    print("📂 Запуск тотального сбора...")
    # Сначала берем 4 гарантированные базы
    all_urls = list(RAW_BASES)
    
    # Добавляем всё остальное из JSON
    try:
        with open('sources/telegram_channels.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            all_urls.extend(list(data.values()) if isinstance(data, dict) else data)
    except: pass

    # Убираем дубли URL чтобы не качать дважды
    all_urls = list(set(all_urls))
    print(f"📡 Опрос {len(all_urls)} источников...")

    raw_configs = set()
    with ThreadPoolExecutor(max_workers=50) as executor:
        for res in executor.map(fetch_url, all_urls):
            raw_configs.update(res)

    unique_by_ip = {}
    for link in raw_configs:
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
    print(f"✅ Итог: {len(res)} уникальных серверов.")