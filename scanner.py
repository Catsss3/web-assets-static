import json
import re
import os
import requests
from concurrent.futures import ThreadPoolExecutor

def fetch_url(url):
    try:
        resp = requests.get(url, timeout=12, headers={'User-Agent': 'Mozilla/5.0'})
        if resp.status_code == 200:
            # Исправленная регулярка: используем двойные кавычки снаружи и экранируем \s
            return re.findall(r"hysteria2://[^\s#\"'<>]+", resp.text, flags=re.IGNORECASE)
    except Exception:
        pass
    return []

def clean_and_parse():
    print("📂 Загрузка источников...")
    try:
        with open('sources/telegram_channels.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            sources = list(data.values()) if isinstance(data, dict) else data
    except Exception as e:
        print(f"❌ Ошибка чтения JSON: {e}")
        return []

    print(f"📡 Начинаю сбор из {len(sources)} источников в 20 потоков...")
    raw_configs = set()
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(fetch_url, sources)
        for found_links in results:
            raw_configs.update(found_links)

    print(f"🔍 Найдено сырых ссылок: {len(raw_configs)}. Чистка дубликатов по IP...")
    
    unique_by_ip = {}
    for link in raw_configs:
        # Убираем возможные лишние символы в конце (точки, запятые)
        clean_link = link.rstrip('.,')
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

    print(f"✅ Готово! Уникальных серверов сохранено: {len(final_links)}")