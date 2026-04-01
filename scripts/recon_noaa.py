import requests
from bs4 import BeautifulSoup
import json

url = "https://www.fisheries.noaa.gov/rules-and-announcements/bulletins?title=&sort_by=created&items_per_page=25"
try:
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    r = requests.get(url, headers=headers, timeout=15)
    print("Status:", r.status_code)
    
    soup = BeautifulSoup(r.text, 'html.parser')
    
    # In Drupal-based government sites like NOAA, lists are often in views-row
    rows = soup.find_all('div', class_='views-row')
    print(f"Found {len(rows)} views-row items")
    
    count = 0
    for row in rows:
        title_el = row.find(['h3', 'h4', 'h2'], class_='title') or row.find('a')
        if not title_el:
            title_el = row.find('div', class_='views-field-title')
            
        region_el = row.find('div', class_='views-field-field-region')
        
        text = title_el.text.strip() if title_el else "Unknown title"
        region = region_el.text.strip() if region_el else ""
        link = row.find('a')
        href = link['href'] if link and link.has_attr('href') else ""
        
        print(f"[{count}] {text} | {region} -> {href}")
        count += 1
        if count > 10: break
except Exception as e:
    print("Error:", e)
