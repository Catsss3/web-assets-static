import json
import re
import os
import requests
import yaml
from concurrent.futures import ThreadPoolExecutor

def fetch_url(url):
    # Убираем мертвые прокси-зеркала, если они есть в ссылке
    url = url.replace('https://mirror.ghproxy.com/', '').replace('https://raw.fastgit.org/', 'https://raw.githubusercontent.com/')
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, timeout=20, headers=headers)
        
        if resp.status_code == 200:
            text = resp.text
            found = []
            
            # 1. Ищем прямые ссылки Hy2
            found.extend(re.findall(r"hysteria2://[^\s#\"'<>]+", text, flags=re.IGNORECASE))
            
            # 2. Если это Clash YAML, вытаскиваем из структуры
            if 'proxies:' in text or url.endswith(('.yaml', '.yml')):
                try:
                    y = yaml.safe_load(text)
                    if isinstance(y, dict) and 'proxies' in y:
                        for p in y['proxies']:
                            if p.get('type') == 'hysteria2':
                                # Собираем ссылку вручную из полей YAML
                                link = f"hysteria2://{p.get('auth')}@{p.get('server')}:{p.get('port')}?insecure={int(p.get('skip-cert-verify', 0))}&sni={p.get('sni', p.get('server'))}#{p.get('name')}"
                                found.append(link)
                except: pass
            
            # 3. Разбиваем построчно для обычных TXT
            if not found:
                for line in text.splitlines():
                    if 'hysteria2://' in line.lower():
                        found.append(line.strip())
            
            return found
    except: pass
    return []

def clean_and_parse():
    print("📂 Загрузка источников...")
    try:
        with open('sources/telegram_channels.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            sources = list(data.values()) if isinstance(data, dict) else data
    except: return []

    print(f"📡 Глубокое сканирование {len(sources)} источников...")
    raw_configs = set()
    
    with ThreadPoolExecutor(max_workers=50) as executor:
        results = executor.map(fetch_url, sources)
        for found_links in results:
            if found_links: raw_configs.update(found_links)

    unique_by_ip = {}
    for link in raw_configs:
        clean_link = link.strip().rstrip('.,;)]}"')
        # Извлекаем IP:PORT для дедупликации
        m = re.search(r'(?:@|^|//)([^:/@\s?#]+:[0-9]+)', clean_link)
        if m:
            ip_port = m.group(1)
            if ip_port not in unique_by_ip:
                unique_by_ip[ip_port] = clean_link

    return list(unique_by_ip.values())

if __name__ == '__main__':
    os.makedirs('providers', exist_ok=True)
    res = clean_and_parse()
    with open('providers/hy2_list.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(res))
    print(f"✅ Итог: {len(res)} уникальных серверов.")