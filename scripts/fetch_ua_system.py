#!/usr/bin/env python3
import json
import os
import hashlib
from datetime import datetime
from bs4 import BeautifulSoup
from curl_cffi import requests
from urllib.parse import urljoin

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "ua_news.json")

# Map of UA System campuses and their news indexes
TARGETS = [
    {
        "name": "UAA Green & Gold News",
        "url": "https://www.uaa.alaska.edu/news/",
        "base_url": "https://www.uaa.alaska.edu"
    },
    {
        "name": "UAF Main News",
        "url": "https://uaf.edu/news/",
        "base_url": "https://uaf.edu"
    }
]

def generate_hash(title: str, link: str) -> str:
    """Generate a stable deduplication hash."""
    return hashlib.md5(f"{title}|{link}".encode()).hexdigest()

def extract_news():
    extracted_items = []
    
    for target in TARGETS:
        try:
            print(f"Scraping [{target['name']}] at {target['url']}...")
            # Use curl_cffi to bypass WAF / strict TLS constraints
            r = requests.get(target['url'], impersonate="chrome110", timeout=15)
            if r.status_code != 200:
                print(f"Warning: Failed to fetch {target['name']} (Status: {r.status_code})")
                continue
                
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # Modern Campus CMS typically wraps news stories in <article> or div with class 'news/post/item'
            articles = soup.find_all(['article', 'div'], class_=lambda c: c and ('news' in c.lower() or 'post' in c.lower() or 'item' in c.lower()))
            
            items_found = 0
            for a in articles:
                # Find the title and link
                title_tag = a.find(['h2', 'h3', 'h4', 'a'])
                if not title_tag:
                    continue
                    
                title = title_tag.text.strip()
                if not title:
                    continue
                    
                link_tag = a.find('a', href=True)
                if not link_tag:
                    continue
                    
                url = link_tag['href']
                # Correct relative URLs
                if url.startswith('/'):
                    url = urljoin(target['base_url'], url)
                    
                # Extract snippet/content if available
                snippet = ""
                p_tag = a.find('p')
                if p_tag and p_tag.text.strip():
                    snippet = p_tag.text.strip()
                    
                # Basic validation
                if len(title) < 5 or "No Title" in title:
                    continue
                
                intel_item = {
                    "id": generate_hash(title, url),
                    "title": title,
                    "link": url,
                    "content": snippet,
                    "source": target['name'],
                    "category": "Education",
                    "priority": "low",  # Standard education tier priority
                    "scraped_at": datetime.utcnow().isoformat() + "Z"
                }
                
                extracted_items.append(intel_item)
                items_found += 1
                
                # Limit to latest 15 per campus to avoid flooding
                if items_found >= 15:
                    break
                    
            print(f"  -> Extracted {items_found} distinct signals.")
            
        except Exception as e:
            print(f"Error extracting from {target['name']}: {e}")
            
    print(f"\nTotal UA System Items Extracted: {len(extracted_items)}")
    
    # Write to local state file
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(extracted_items, f, indent=2)
        
    print(f"Data reliably serialized to {OUTPUT_FILE}")

if __name__ == "__main__":
    extract_news()
