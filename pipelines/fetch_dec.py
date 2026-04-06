import collections
import datetime
import hashlib
import json
import logging
import os
import requests
from bs4 import BeautifulSoup
from dateutil import parser
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

DEC_SEARCH_URL = "https://dec.alaska.gov/Applications/SPAR/PublicMVC/PERP/SpillSearch"

def fetch_dec_spills():
    logger.info("============================================================")
    logger.info("Alaska DEC SPAR Scraper")
    logger.info("============================================================")

    session = requests.Session()

    logger.info("📡 Negotiating ASP.NET session token...")
    try:
        r = session.get(DEC_SEARCH_URL, verify=False, timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        token = soup.find('input', {'name': '__RequestVerificationToken'})
        if not token:
            logger.warning("⚠ No __RequestVerificationToken found. Attempting POST without it.")
            token_val = ''
        else:
            token_val = token['value']
    except Exception as e:
        logger.error(f"❌ Handshake failed: {e}")
        return []

    # Fetch last 14 days of spills
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=14)

    payload = {
        '__RequestVerificationToken': token_val,
        'Spill_DateFrom': start_date.strftime('%m/%d/%Y'),
        'Spill_DateTo': end_date.strftime('%m/%d/%Y'),
        'Spill_SearchButton': 'Search'
    }

    logger.info(f"⏳ POSTing search from {payload['Spill_DateFrom']} to {payload['Spill_DateTo']}")
    try:
        r2 = session.post(DEC_SEARCH_URL, data=payload, verify=False, timeout=20)
        soup2 = BeautifulSoup(r2.text, 'html.parser')
        
        tables = soup2.find_all('table')
        if len(tables) < 2:
            logger.warning("⚠ No results table found in response payload.")
            return []

        # The last table is usually the results grid
        results_grid = tables[-1]
        rows = results_grid.find_all('tr')
        
        extracted_spills = []
        # Skip header row
        for row in rows[1:]:
            cols = row.find_all('td')
            if len(cols) >= 4:
                spill_num = cols[0].text.strip()
                spill_name = cols[1].text.strip()
                spill_date = cols[2].text.strip()
                facility = cols[3].text.strip()
                
                try:
                    dt = parser.parse(spill_date)
                    iso_date = dt.isoformat()
                except:
                    iso_date = spill_date
                    
                raw_str = f"{spill_num}{spill_name}{iso_date}"
                hash_id = hashlib.sha256(raw_str.encode('utf-8')).hexdigest()
                
                spill_obj = {
                    "id": spill_num,
                    "hash": hash_id,
                    "title": spill_name,
                    "content": f"Facility/Location: {facility}",
                    "published": iso_date,
                    "timestamp": iso_date,
                    "source": "Alaska DEC Spill Response",
                    "url": DEC_SEARCH_URL,
                    "category": "Environment",
                    "topic": "Hazmat",
                    "severity": "high",
                    "location": facility,
                    "sourceLean": "neutral"
                }
                
                extracted_spills.append(spill_obj)
        
        logger.info(f"✓ Parsed {len(extracted_spills)} recent environmental spills")
        
        os.makedirs('data', exist_ok=True)
        with open('data/dec_spills.json', 'w') as f:
            json.dump(extracted_spills, f, indent=2)
            
        return extracted_spills

    except Exception as e:
        logger.error(f"❌ Extraction POST failed: {e}")
        return []

if __name__ == "__main__":
    fetch_dec_spills()
