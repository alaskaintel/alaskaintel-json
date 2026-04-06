import os
import json
import hashlib
from datetime import datetime
from curl_cffi import requests
from bs4 import BeautifulSoup

def fetch_asd_news():
    print("📡 Fetching Anchorage School District (ASD) News...")
    url = "https://www.asdk12.org/all-news"
    
    try:
        r = requests.get(url, impersonate="chrome110", timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        items = []
        for a in soup.find_all('a'):
            title = a.text.strip()
            href = a.get('href', '')
            
            # Identify Blackboard news nodes and external press releases
            if len(title) > 10 and ('/post/' in href.lower() or '/article/' in href.lower() or 'news' in title.lower() or 'recap' in title.lower()):
                
                if href.startswith('/'):
                    href = "https://www.asdk12.org" + href
                
                # Prevent deduplication
                if any(x['url'] == href or x['title'] == title for x in items):
                    continue
                    
                article = {
                    "id": hashlib.sha256(href.encode()).hexdigest(),
                    "title": title,
                    "content": title,
                    "published": datetime.now().isoformat() + "Z",
                    "timestamp": datetime.now().isoformat() + "Z",
                    "source": "Anchorage School District",
                    "url": href,
                    "category": "Education",
                    "topic": "Community",
                    "severity": 10,
                    "location": "Anchorage, AK",
                    "sourceLean": "center",
                    "hash": hashlib.sha256((title + href).encode()).hexdigest()
                }
                items.append(article)
                
        # Limit to the top 20 news items to prevent overload
        items = items[:20]
        
        payload = {
            "type": "FeatureCollection",
            "features": items
        }
        
        os.makedirs("data", exist_ok=True)
        with open("data/asd_news.json", "w") as f:
            json.dump(payload, f, indent=2)
            
        print(f"  ✓ Retrieved {len(items)} ASD News articles")
        
    except Exception as e:
        print(f"❌ Error fetching ASD News: {e}")

if __name__ == "__main__":
    fetch_asd_news()
