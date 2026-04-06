import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import os
import concurrent.futures

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
}

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def find_rss_on_domain(feed_url):
    domain = urlparse(feed_url).netloc
    scheme = urlparse(feed_url).scheme or 'https'
    base_url = f"{scheme}://{domain}"
    
    try:
        r = requests.get(base_url, headers=HEADERS, timeout=8, verify=False)
        if r.status_code != 200:
            return None
            
        soup = BeautifulSoup(r.text, 'html.parser')
        links = soup.find_all('link', type=['application/rss+xml', 'application/atom+xml'])
        
        found = []
        for link in links:
            href = link.get('href')
            if href:
                found.append(urljoin(base_url, href))
                
        if not found:
            a_tags = soup.find_all('a', href=True)
            for a in a_tags:
                href = a['href'].lower()
                text = a.get_text().lower()
                if 'rss' in href or '/feed' in href or 'rss' in text:
                    found.append(urljoin(base_url, a['href']))
                    
        # Clean duplicates
        found = list(set(found))
        
        # Test found feeds
        for f in found:
            try:
                fr = requests.get(f, headers=HEADERS, timeout=5, verify=False)
                if fr.status_code == 200 and ('<rss' in fr.text.lower() or '<feed' in fr.text.lower() or 'xmlns' in fr.text.lower() or '<rdf:' in fr.text.lower()):
                    return f
            except:
                continue
                
        # If nothing found, test common paths
        common = [urljoin(base_url, '/feed'), urljoin(base_url, '/rss'), urljoin(base_url, '/rss.xml')]
        for c in common:
            try:
                fr = requests.get(c, headers=HEADERS, timeout=3, verify=False)
                if fr.status_code == 200 and ('<rss' in fr.text.lower() or '<feed' in fr.text.lower() or 'xmlns' in fr.text.lower()):
                    return c
            except:
                continue
                
        return None
    except Exception as e:
        return None

def process_feed(feed):
    old_url = feed['url']
    new_url = find_rss_on_domain(old_url)
    if new_url and new_url != old_url:
        print(f"✅ Repaired: {feed['name']} -> {new_url}")
        return old_url, new_url
    else:
        print(f"❌ Failed: {feed['name']} ({old_url})")
        return None

def main():
    report_path = 'data/feed_health_report.json'
    try:
        with open(report_path, 'r') as f:
            report = json.load(f)
    except FileNotFoundError:
        print(f"Report not found at {report_path}")
        return
        
    replacements = {}
    errors = [f for f in report.get('feeds', []) if f.get('status') in ['error', 'warning']]
    
    print(f"Found {len(errors)} broken feeds to investigate.")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(process_feed, feed): feed for feed in errors}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                replacements[res[0]] = res[1]
            
    print(f"\nFound verified replacements for {len(replacements)} feeds.")
    
    if not replacements:
        return
        
    with open('data/healed_replacements.json', 'w') as f:
        json.dump(replacements, f, indent=2)
        
    # Replace in fetch_intel.py
    fetch_path = 'fetch_intel.py'
    if os.path.exists(fetch_path):
        with open(fetch_path, 'r') as f:
            content = f.read()
            
        for old_u, new_u in replacements.items():
            content = content.replace(f'"{old_u}"', f'"{new_u}"')
            content = content.replace(f"'{old_u}'", f"'{new_u}'")
            
        with open(fetch_path, 'w') as f:
            f.write(content)
        print("Updated fetch_intel.py")
            
    # Replace in feedCatalog.ts
    catalog_path = '../../frontends/www.alaskaintel.com/src/data/feedCatalog.ts'
    if os.path.exists(catalog_path):
        with open(catalog_path, 'r') as f:
            content = f.read()
            
        for old_u, new_u in replacements.items():
            content = content.replace(f'"{old_u}"', f'"{new_u}"')
            content = content.replace(f"'{old_u}'", f"'{new_u}'")
            
        with open(catalog_path, 'w') as f:
            f.write(content)
        print("Updated feedCatalog.ts")

if __name__ == '__main__':
    main()
