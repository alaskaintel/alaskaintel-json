import logging
import json
import hashlib
import os
from datetime import datetime
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

NOAA_BULLETINS_URL = "https://www.fisheries.noaa.gov/rules-and-announcements/bulletins?title=&sort_by=created&items_per_page=50"

def fetch_noaa_bulletins():
    logger.info("============================================================")
    logger.info("NOAA Fisheries Alaska - Information Bulletins & Closures")
    logger.info("============================================================")

    extracted_notices = []

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
        }
        logger.info(f"📡 Requesting NOAA Bulletins from {NOAA_BULLETINS_URL}")
        r = requests.get(NOAA_BULLETINS_URL, headers=headers, timeout=15)
        
        if r.status_code != 200:
            logger.error(f"❌ Failed to reach NOAA: HTTP {r.status_code}")
            return []
            
        logger.info(f"✓ Connected to NOAA server. Parsing {len(r.text)} bytes of DOM...")
        soup = BeautifulSoup(r.text, 'html.parser')
        
        teasers = soup.find_all('div', class_='teaser')
        logger.info(f"🔍 Found {len(teasers)} bulletin blocks. Filtering for Alaska region...")
        
        for index, item in enumerate(teasers):
            title_node = item.find('h4', class_='teaser__title')
            
            if not title_node:
                continue
                
            title_text = title_node.text.strip()
            link_node = title_node.find('a', class_='teaser__title-link')
            
            href = link_node.get('href', '') if link_node else ''
            if href and not href.startswith('http'):
                url_href = f"https://www.fisheries.noaa.gov{href}"
            else:
                url_href = href or NOAA_BULLETINS_URL
                
            summary_node = item.find('div', class_='teaser__summary')
            summary = summary_node.text.strip() if summary_node else "No summary available."
            
            date_node = item.find('span', class_='teaser__meta-date')
            pub_date_str = date_node.text.strip() if date_node else "Unknown Date"
            
            region_node = item.find('span', class_=lambda x: x and x.startswith('region_label_'))
            region_text = region_node.text.strip() if region_node else ""
            
            # Filter logic: We only want Alaska, Pacific Northwest, or National
            # Or if "Alaska", "Bering", "Aleutian" is in the title/summary.
            valid_targets = ['alaska', 'bering', 'aleutian', 'pacific', 'national']
            target_str = (title_text + " " + summary + " " + region_text).lower()
            
            if not any(target in target_str for target in valid_targets):
                continue
                
            # Valid Alaska/Pacific NOAA Bulletin
            raw_str = f"{title_text}{pub_date_str}"
            hash_id = hashlib.sha256(raw_str.encode('utf-8')).hexdigest()
            
            iso_date = datetime.now().isoformat()
            
            spill_obj = {
                "id": f"NOAA-IB-{index}",
                "hash": hash_id,
                "title": f"NOAA Fisheries: {title_text}",
                "content": f"{summary}\n\nRegion: {region_text} | Date: {pub_date_str}",
                "published": iso_date,
                "timestamp": iso_date,
                "source": "NOAA Fisheries",
                "url": url_href,
                "category": "Government",
                "topic": "Environment",
                "severity": "medium",
                "location": "Alaska Oceanic",
                "sourceLean": "neutral"
            }
            extracted_notices.append(spill_obj)
            
        logger.info(f"✓ Successfully extracted {len(extracted_notices)} active Alaska/Pacific NOAA Bulletins.")
                
    except Exception as e:
        logger.error(f"❌ Processing failed: {e}")
        
    if extracted_notices:
        os.makedirs('data', exist_ok=True)
        with open('data/fisheries.json', 'w') as f:
            json.dump(extracted_notices, f, indent=2)
            
    return extracted_notices

if __name__ == "__main__":
    fetch_noaa_bulletins()
