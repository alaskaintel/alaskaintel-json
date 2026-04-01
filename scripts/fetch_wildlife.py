#!/usr/bin/env python3
"""
Alaska Intel - Dedicated Fish & Wildlife Aggregator
Executes the Playwright node scraper to bypass government WAFs, formats the telemetry, and pushes to Cloudflare D1.
"""

import os
import json
import hashlib
import urllib.request
import subprocess
from datetime import datetime, timezone

def fetch_wildlife_feeds():
    print("Executing Playwright Headless Scraper (WAF Bypass)...")
    
    # Run the node scraper
    script_path = os.path.join(os.path.dirname(__file__), "scrape_wildlife.js")
    result = subprocess.run(["node", script_path], capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Scraper Error: {result.stderr}")
        return []
        
    try:
        # Find the JSON array line in case of extraneous stdout
        stdout_lines = result.stdout.strip().split('\n')
        json_line = next((line for line in stdout_lines if line.startswith('[') and line.endswith(']')), "[]")
        raw_items = json.loads(json_line)
    except Exception as e:
        print(f"Failed to decode scraper JSON: {e}")
        return []

    signals = []
    
    for item in raw_items:
        link = item.get('link', '')
        title = item.get('title', 'Unknown Title')
        timestamp = item.get('timestamp', datetime.now(timezone.utc).isoformat())
        source = item.get('source', 'Unknown Source')
        
        # Derive Location
        lat, lng = None, None
        location_str = ""
        
        title_lower = title.lower()
        if "juneau" in title_lower or "southeast" in title_lower:
            lat, lng = 58.3019, -134.4197
            location_str = "Juneau, AK"
        elif "anchorage" in title_lower:
            lat, lng = 61.2181, -149.9003
            location_str = "Anchorage, AK"
        elif "fairbanks" in title_lower:
            lat, lng = 64.8378, -147.7164
            location_str = "Fairbanks, AK"
        elif "bristol bay" in title_lower:
            lat, lng = 58.8392, -157.0013
            location_str = "Bristol Bay, AK"
        elif "cook inlet" in title_lower or "kenai" in title_lower:
            lat, lng = 60.5544, -151.2583
            location_str = "Cook Inlet, AK"
        elif "kodiak" in title_lower:
            lat, lng = 57.7900, -152.4072
            location_str = "Kodiak, AK"
            
        # Generate unique hash
        hash_input = f"{link}{title}{timestamp}"
        sig_hash = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()
        
        category = "Wildlife" if "US Fish" in source else "Fisheries"
        
        signal = {
            "hash": sig_hash,
            "title": title,
            "summary": "Official update released by the " + source + ".",
            "source": source,
            "sourceUrl": "https://adfg.alaska.gov" if "ADF&G" in source else "https://www.fws.gov",
            "articleUrl": link,
            "category": category,
            "topic": category,
            "timestamp": timestamp,
            "impactScore": 60,
            "lat": lat,
            "lng": lng,
            "location": location_str
        }
        
        # Boost impact for Emergency Orders
        if "emergency order" in title_lower or "emergency" in title_lower:
            signal["impactScore"] = 85
            
        signals.append(signal)

    print(f"Extracted {len(signals)} authenticated Wildlife/Fishery signals.")
    return signals

def push_to_d1(signals):
    if not signals:
        return
        
    url = "https://alaskaintel-api.kbdesignphoto.workers.dev/ingest"
    
    try:
        req = urllib.request.Request(url, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "AlaskaIntel-Wildlife/1.0")
        
        chunk_size = 50
        uploaded = 0
        
        for i in range(0, len(signals), chunk_size):
            chunk = signals[i:i + chunk_size]
            data = json.dumps(chunk).encode('utf-8')
            req.data = data
            
            with urllib.request.urlopen(req) as response:
                if response.getcode() == 200:
                    uploaded += len(chunk)
                    
        print(f"Successfully synced {uploaded} signals to Cloudflare D1.")
        
    except Exception as e:
        print(f"Critical error pushing to D1: {e}")

if __name__ == "__main__":
    print("="*50)
    print("AlaskaIntel - Wildlife Pipeline Initiated")
    print("="*50)
    
    telemetry = fetch_wildlife_feeds()
    push_to_d1(telemetry)
