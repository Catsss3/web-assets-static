import json
import re
import os
import requests
from concurrent.futures import ThreadPoolExecutor

def fetch_url(url):
    try:
        # Увеличиваем таймаут для жирных файлов GitHub
        timeout = 20 if "raw.githubusercontent.com" in url else 12
        resp = requests.get(url, timeout=timeout, headers={'User-Agent': 'Mozilla/5.0'})
        
        if resp.status_code == 200:
            # Ищем все hysteria2 ссылки
            found = re.findall(r"hysteria2://[^\s#\"'<>]+", resp.text, flags=re.IGNORECASE)
            return found
    except Exception:
        pass
    return []

def clean_and_parse():
    print("📂 Загрузка единого хранилища источников...")
    try:
        with open('sources/telegram_channels.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            sources = list(data.values()) if isinstance(data, dict) else data
    except Exception as e:
        print(f"❌ Ошибка: файл источников не найден или поврежден: {e}")
        return []

    print(f"📡 Запуск сканирования ({len(sources)} источников)...")
    raw_configs = set()
    
    # 30 потоков, чтобы быстро прожевать и базы, и каналы
    with ThreadPoolExecutor(max_workers=30) as executor:
        results = executor.map(fetch_url, sources)
        for found_links in results:
            raw_configs.update(found_links)

    print(f"🔍 Найдено всего: {len(raw_configs)}. Фильтрация дубликатов по IP...")
    
    unique_by_ip = {}
    for link in raw_configs:
        clean_link = link.rstrip('.,')
        # Ищем IP:PORT
        m = re.search(r'(?:@|^|//)([^:/@\s]+:[0-9]+)', clean_link)
        if m:
            ip_port = m.group(1)
            if ip_port not in unique_by_ip:
                unique_by_ip[ip_port] = clean_link

    return list(unique_by_ip.values())

if __name__ == '__main__':
    os.makedirs('providers', exist_ok=True)
    final_links = clean_and_parse()
    
    out_path = os.path.join('providers', 'hy2_list.txt')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(final_links))

    print(f"✅ Готово! Уникальных серверов: {len(final_links)}")