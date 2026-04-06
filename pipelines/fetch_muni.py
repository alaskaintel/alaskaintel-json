import requests
import json
import logging
import os
import hashlib
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

API_URL = "https://www.muni.org/PublicNotice/_api/web/lists/getbytitle('Pages')/items?$select=Title,Id,Created,Modified,Event_x0020_Location,PublicNoticeEventStart,OData__EndDate,File/ServerRelativeUrl&$expand=File&$orderby=Created desc&$top=100"
OUTPUT_FILE = "data/muni_notices.json"
HEADERS = {
    'Accept': 'application/json;odata=verbose',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
}

def clean_html(text):
    if not text:
        return ""
    import re
    return re.sub(r'<[^>]+>', ' ', text).strip()

def scrape_muni():
    logging.info(f"Starting Anchorage Muni API scrape for {API_URL}")
    items = []

    try:
        resp = requests.get(API_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("d", {}).get("results", [])
        
        for doc in results:
            title = doc.get("Title", "")
            doc_id = doc.get("Id", "")
            
            if not title:
                continue
                
            created_date = doc.get("Created")
            event_start = doc.get("PublicNoticeEventStart")
            location = doc.get("Event_x0020_Location", "")
            
            file_ref = doc.get("File", {}).get("ServerRelativeUrl", "")
            if file_ref:
                full_url = "https://www.muni.org" + file_ref
            else:
                full_url = f"https://www.muni.org/PublicNotice/Pages/DispForm.aspx?ID={doc_id}"
                
            dt_str = datetime.utcnow().isoformat() + "Z"
            if created_date:
                dt_str = created_date
                
            item = {
                "hash": f"muni_{doc_id or hashlib.md5(full_url.encode()).hexdigest()}",
                "id": f"muni_{doc_id or hashlib.md5(full_url.encode()).hexdigest()}",
                "title": title[:150] + "..." if len(title) > 150 else title,
                "source": "Anchorage Municipality",
                "timestamp": dt_str,
                "original_date": str(event_start or created_date),
                "url": full_url,
                "location": "Anchorage",
                "publication": "Muni Public Notices",
                "type": "public_notice",
                "confidence": 0.95
            }
            if location:
                item["description"] = f"Location: {clean_html(location)}"
                
            items.append(item)

        logging.info(f"Successfully scraped {len(items)} notices from Anchorage Muni.")

    except Exception as e:
        logging.error(f"Error scraping Muni: {e}")

    return items

if __name__ == "__main__":
    notices = scrape_muni()
    if notices:
        import os
        os.makedirs('data', exist_ok=True)
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(notices, f, indent=2)
        logging.info(f"Saved {len(notices)} Muni traces to {OUTPUT_FILE}")
