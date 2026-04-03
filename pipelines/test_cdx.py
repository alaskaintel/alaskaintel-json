import requests
import json
from collections import Counter

url = "http://web.archive.org/cdx/search/cdx"
params = {
    "url": "dailydispatch.dps.alaska.gov*",
    "output": "json",
    "limit": 100000,
    "fl": "timestamp,original,mimetype,statuscode",
    "filter": "statuscode:200"
}

print("Querying CDX API for dailydispatch.dps.alaska.gov ...")
try:
    resp = requests.get(url, params=params, timeout=30)
    data = resp.json()
    
    if len(data) > 1:
        records = data[1:]
        print(f"Total matching snapshots found: {len(records)}")
        
        years = Counter()
        incident_urls = 0
        
        earliest = records[0][0]
        latest = records[-1][0]
        
        for r in records:
            ts = r[0]
            year = ts[:4]
            years[year] += 1
            
            if "DisplayIncident" in r[1]:
                incident_urls += 1
                
        print(f"Date range: {earliest} to {latest}")
        print(f"Total specific Incident page snapshots: {incident_urls}")
        print("Breakdown by Year:")
        for y, count in sorted(years.items()):
            print(f"  {y}: {count} snapshots")
    else:
        print("No records found.")
except Exception as e:
    print(f"Error: {e}")
