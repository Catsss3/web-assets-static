import json
import re
import os
import requests
from concurrent.futures import ThreadPoolExecutor

def fetch_url(url):
    try:
        # Увеличиваем таймаут и добавляем заголовки для GitHub
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, timeout=25, headers=headers)
        
        if resp.status_code == 200:
            text = resp.text
            # 1. Сначала ищем классической регуляркой
            found = re.findall(r"hysteria2://[^\s#\"'<>]+", text, flags=re.IGNORECASE)
            
            # 2. ДОПОЛНИТЕЛЬНО: Если файл - это просто список в столбик, разбиваем по строкам
            if not found or len(found) < 5:
                lines = text.splitlines()
                for line in lines:
                    line = line.strip()
                    if line.lower().startswith("hysteria2://"):
                        found.append(line)
            
            return list(set(found)) # Убираем дубли внутри одного файла
    except Exception as e:
        print(f"⚠️ Ошибка на {url[:30]}... : {e}")
    return []

def clean_and_parse():
    print("📂 Загрузка источников из JSON...")
    try:
        with open('sources/telegram_channels.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            sources = list(data.values()) if isinstance(data, dict) else data
    except Exception as e:
        print(f"❌ Критическая ошибка JSON: {e}")
        return []

    print(f"📡 Сбор данных из {len(sources)} источников...")
    raw_configs = set()
    
    # Используем 40 потоков для скорости
    with ThreadPoolExecutor(max_workers=40) as executor:
        results = executor.map(fetch_url, sources)
        for found_links in results:
            if found_links:
                raw_configs.update(found_links)

    print(f"🔍 Найдено сырых строк: {len(raw_configs)}. Считаю уникальные IP...")
    
    unique_by_ip = {}
    for link in raw_configs:
        # Очистка от мусора
        clean_link = link.strip().rstrip('.,;)]}"')
        
        # Более жесткий поиск IP:PORT
        m = re.search(r'(?:@|^|//)([^:/@\s?#]+:[0-9]+)', clean_link)
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

    print(f"✅ Готово! Финальный улов: {len(final_links)} уникальных серверов.")