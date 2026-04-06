#!/usr/bin/env python3
import json
import os
import hashlib
import concurrent.futures
from datetime import datetime
from bs4 import BeautifulSoup
from curl_cffi import requests
from urllib.parse import urljoin

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "k12_districts.json")
DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "ak_schools.json")

try:
    with open(DATA_FILE, 'r') as f:
        _schools = json.load(f)
    
    # Map the deep-level Schools dataset to the scraper's format requirements
    TARGETS = [
        {
            "name": d["name"],
            "url": d["url"],
            "base_url": d["url"],
            "district": d.get("district_name", "Unknown District")
        }
        for d in _schools if "url" in d
    ]
except Exception as e:
    print(f"Error loading K-12 dynamic targets: {e}")
    TARGETS = []

def generate_hash(title: str, link: str) -> str:
    """Generate a stable deduplication hash."""
    return hashlib.md5(f"{title}|{link}".encode()).hexdigest()

def scrape_school(target):
    """Worker function to scrape a single school or district."""
    extracted = []
    try:
        r = requests.get(target['url'], impersonate="chrome110", timeout=15)
        
        if r.status_code != 200:
            return extracted
            
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Target news article wrappers
        articles = soup.find_all(['article', 'div'], class_=lambda c: c and ('news' in c.lower() or 'post' in c.lower() or 'item' in c.lower() or 'article' in c.lower()))
        
        items_found = 0
        seen_titles = set()
        
        for a in articles:
            # Find the title and link
            title_tag = a.find(['h1', 'h2', 'h3', 'h4', 'a'])
            if not title_tag:
                continue
                
            title = title_tag.text.strip()
            if not title or title in seen_titles:
                continue
                
            seen_titles.add(title)
            
            link_tag = a.find('a', href=True)
            if not link_tag:
                continue
                
            url = link_tag['href']
            if url.startswith('/'):
                url = urljoin(target['base_url'], url)
                
            snippet = ""
            p_tag = a.find('p')
            if p_tag and p_tag.text.strip():
                snippet = p_tag.text.strip()
                
            # Basic validation
            if len(title) < 5 or "No Title" in title or "Read More" == title or "News" == title:
                continue
            
            intel_item = {
                "id": generate_hash(title, url),
                "title": title,
                "link": url,
                "content": snippet,
                "source": target['name'],
                "category": "Education",
                "priority": "low",
                "scraped_at": datetime.utcnow().isoformat() + "Z"
            }
            
            extracted.append(intel_item)
            items_found += 1
            
            # Cap at 5 per school (to avoid dominating radar with 700 schools)
            if items_found >= 5:
                break
                
    except Exception as e:
        pass # Silently drop timeouts on hundreds of domains to keep logs clean
        
    return extracted

def extract_k12_news():
    extracted_items = []
    
    print(f"Executing Deep-Level Extraction Engine across {len(TARGETS)} K-12 Endpoints...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_target = {executor.submit(scrape_school, target): target for target in TARGETS}
        
        for future in concurrent.futures.as_completed(future_to_target):
            try:
                data = future.result()
                extracted_items.extend(data)
            except Exception as e:
                pass
                
    print(f"\nTotal Individual Signals Extracted: {len(extracted_items)}")
    
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(extracted_items, f, indent=2)
        
    print(f"Data reliably serialized to {OUTPUT_FILE}")

    # === Ingest K12 signals into Cloudflare D1 ===
    if not extracted_items:
        print("No K12 signals to ingest.")
        return

    # Transform to the standard signal schema used by /ingest
    now_iso = datetime.utcnow().isoformat() + "Z"
    signals = []
    for item in extracted_items:
        signals.append({
            "id":           item.get("id", hashlib.md5(item.get("title","").encode()).hexdigest()),
            "title":        item.get("title", ""),
            "summary":      item.get("content", ""),
            "source":       item.get("source", "Alaska K-12"),
            "articleUrl":   item.get("link", ""),
            "imageUrl":     None,
            "timestamp":    item.get("scraped_at", now_iso),
            "published":    item.get("scraped_at", now_iso),
            "category":     "Education",
            "sector":       "education",
            "region":       None,
            "urgency":      "background",
            "impactScore":  40,
            "lat":          None,
            "lng":          None,
            "entitySlugs":  [],
            "dataTag":      None,
            "sourceAttribution": f"Source: {item.get('source', 'Alaska K-12')}",
        })

    try:
        import urllib.request
        print(f"\n☁️  Syncing {len(signals[:500])} K12 signals to Cloudflare D1...")
        url = "https://api01.alaskaintel.com/ingest"
        req = urllib.request.Request(url, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "AlaskaIntel-Pipeline/1.0")
        ingest_secret = os.environ.get("INGEST_SECRET")
        if ingest_secret:
            req.add_header("Authorization", f"Bearer {ingest_secret}")
        json_data = json.dumps(signals[:500]).encode("utf-8")
        with urllib.request.urlopen(req, data=json_data, timeout=30) as response:
            res = json.loads(response.read().decode("utf-8"))
            print(f"✓ K12 → D1 sync complete (Inserted: {res.get('inserted', '?')})")
    except Exception as e:
        print(f"Warning: K12 D1 ingest failed: {e}")

if __name__ == "__main__":
    extract_k12_news()
