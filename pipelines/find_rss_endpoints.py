#!/usr/bin/env python3
"""
Autonomous RSS Discovery Engine
Crawls the homepages of the provided deleted feeds to heuristically discover
updated or new RSS/Atom endpoints hidden in the <head> metadata.
"""

import ast
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import os
import json

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"}

def get_deleted_feeds():
    # Use Git to grab the old version of fetch_intel.py
    os.system("git show HEAD:scripts/fetch_intel.py > /tmp/old_fetch_intel.py")
    
    def extract_feeds(filename):
        try:
            with open(filename) as f: contents = f.read()
            tree = ast.parse(contents)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == 'FEEDS':
                            feeds = []
                            for el in node.value.elts:
                                feed = {}
                                for k, v in zip(el.keys, el.values):
                                    if hasattr(v, 'value'):
                                        feed[k.value] = v.value
                                feeds.append(feed)
                            return feeds
        except Exception:
            pass
        return []

    old = extract_feeds('/tmp/old_fetch_intel.py')
    new = extract_feeds('scripts/fetch_intel.py')
    
    old_urls = {f.get('url') for f in old if f.get('url')}
    new_urls = {f.get('url') for f in new if f.get('url')}
    deleted_urls = old_urls - new_urls
    
    return [f for f in old if f.get('url') in deleted_urls]

def find_rss_on_domain(feed):
    original_url = feed['url']
    domain = urlparse(original_url).netloc
    scheme = urlparse(original_url).scheme or 'https'
    
    base_url = f"{scheme}://{domain}"
    
    print(f"\\n🔍 Scanning {base_url} for '{feed['name']}'...")
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        r = requests.get(base_url, headers=HEADERS, timeout=10, verify=False)
        if r.status_code != 200:
            print(f"  ⚠️  HTTP {r.status_code}")
            return None
            
        soup = BeautifulSoup(r.text, 'html.parser')
        # Look for RSS or ATOM autodiscovery tags
        links = soup.find_all('link', type=['application/rss+xml', 'application/atom+xml'])
        
        found = []
        for link in links:
            href = link.get('href')
            if href:
                # Resolve relative URLs
                full_url = urljoin(base_url, href)
                found.append(full_url)
                
        # Fallback: look for common <a> links mentioning RSS
        if not found:
            a_tags = soup.find_all('a', href=True)
            for a in a_tags:
                href = a['href'].lower()
                text = a.get_text().lower()
                if 'rss' in href or 'rss' in text:
                    full_url = urljoin(base_url, a['href'])
                    found.append(full_url)
                    
        # Remove duplicates
        found = list(set(found))
        
        if found:
            for f in found:
                print(f"  ✅ Discovered: {f}")
            return {"feed": feed, "discovered": found}
        else:
            print(f"  ❌ No RSS feeds detected on homepage.")
            return None
            
    except Exception as e:
        print(f"  ⚠️  Connection Error: {type(e).__name__}")
        return None

def main():
    print("="*60)
    print("Alaska Intel - Autonomous RSS Discovery Engine")
    print("="*60)
    
    deleted_feeds = get_deleted_feeds()
    print(f"Found {len(deleted_feeds)} orphaned feeds to investigate.\\n")
    
    results = []
    
    # Only test the first 25 domains to save execution time in this run
    for feed in deleted_feeds[:25]:
        res = find_rss_on_domain(feed)
        if res:
            results.append(res)
            
    print("\\n" + "="*60)
    if results:
        print(f"🎉 Successfully auto-discovered replacement feeds for {len(results)} targets!")
        with open('data/discovered_feeds.json', 'w') as f:
            json.dump(results, f, indent=2)
        print("Data saved to data/discovered_feeds.json")
    else:
        print("No replacement feeds could be automatically discovered.")

if __name__ == "__main__":
    main()
