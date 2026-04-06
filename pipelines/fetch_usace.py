import logging
import json
import hashlib
import os
from datetime import datetime
from curl_cffi import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

USACE_URL = "https://www.poa.usace.army.mil/Missions/Regulatory/Public-Notices/"

def fetch_usace_notices():
    logger.info("============================================================")
    logger.info("USACE Alaska District Scraper")
    logger.info("============================================================")

    extracted_notices = []

    try:
        logger.info(f"📡 Executing JA3-impersonated handshake to {USACE_URL}")
        r = requests.get(USACE_URL, impersonate="chrome116", verify=False, timeout=15)
        
        if r.status_code != 200:
            logger.error(f"❌ Handshake failed: {r.status_code} - {r.text[:200]}")
            return []
            
        logger.info(f"✓ Handshake successful. Parsing {len(r.text)} bytes of DOM...")
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # The public notices are inside <section class="alist"><ul ...>
        # Each notice is an <li> containing <div class="desc">
        notice_items = soup.find_all('div', class_='desc')
        
        if not notice_items:
            logger.error("❌ Could not locate the public notice data grid (div.desc).")
            return []
            
        logger.info(f"🔍 Found data matrix with {len(notice_items)} potential records.")
        
        for item in notice_items:
            # Title & Link from <h3><a class="title">...</a></h3>
            title_el = item.find('a', class_='title')
            if not title_el:
                continue
                
            spill_name = title_el.text.strip()
            url_href = title_el.get('href', USACE_URL)
            if not url_href.startswith('http'):
                url_href = "https://www.poa.usace.army.mil" + url_href
                
            # Expiration date from <p class="standout">Expiration date: ...</p>
            exp_el = item.find('p', class_='standout')
            spill_date = ""
            if exp_el:
                spill_date = exp_el.text.replace('Expiration date:', '').strip()
                
            # The notice number is usually the start of the title, like "POA-2025-00211"
            spill_num = spill_name.split()[0] if spill_name else "Unknown"
            
            if not spill_name:
                continue
                
            raw_str = f"{spill_num}{spill_name}{spill_date}"
            hash_id = hashlib.sha256(raw_str.encode('utf-8')).hexdigest()
            
            iso_date = datetime.now().isoformat()
            
            spill_obj = {
                "id": spill_num,
                "hash": hash_id,
                "title": f"USACE Notice: {spill_name}",
                "content": f"Notice Reference: {spill_num} | Expiration Date: {spill_date}",
                "published": iso_date,
                "timestamp": iso_date,
                "source": "USACE Alaska District",
                "url": url_href,
                "category": "Government",
                "topic": "Infrastructure",
                "severity": "medium",
                "location": "Alaska Statewide",
                "sourceLean": "neutral"
            }
            extracted_notices.append(spill_obj)
                
        logger.info(f"✓ Successfully extracted {len(extracted_notices)} active USACE permits/notices.")
                
    except Exception as e:
        logger.error(f"❌ Processing failed: {e}")
        
    if extracted_notices:
        os.makedirs('data', exist_ok=True)
        with open('data/usace_notices.json', 'w') as f:
            json.dump(extracted_notices, f, indent=2)
            
    return extracted_notices

if __name__ == "__main__":
    fetch_usace_notices()
