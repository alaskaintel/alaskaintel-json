#!/usr/bin/env python3
"""
AST Deep Stolen Vehicle Crawler
Iterates through thousands of pages of historic Alaska Trooper dispatches.
Extracts only incidents tagged/titled with Stolen Vehicles.
Merges them into data/ast_logs.json.
"""

import os
import json
import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

from geo_dict import geocode_text
from geo_milepost import geocode_milemarker
from scrape_ast import (
    generate_hash, extract_entities, infer_region,
    CHROME_UA, BASE_URL, FILE_PATH
)

DISPATCH_LIST_URL = BASE_URL + '/Home/Display'

def load_data():
    if os.path.exists(FILE_PATH):
        try:
            with open(FILE_PATH, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_data(data):
    os.makedirs('data', exist_ok=True)
    with open(FILE_PATH, 'w') as f:
        json.dump(data, f, indent=2)

def is_stolen_vehicle(title, type_val, text):
    lower_t = (title or '').lower() + (type_val or '').lower() + (text or '').lower()
    return 'stolen vehicle' in lower_t or 'vehicle theft' in lower_t

def process_date(target_date, existing_hashes):
    date_str = target_date.strftime("%-m/%-d/%Y")
    query_param = f"?dateReceived={date_str}%2012:00:00%20AM"
    print(f"  [Scraping Date {date_str}] ...")
    try:
        resp = requests.get(
            f"{DISPATCH_LIST_URL}{query_param}",
            headers={'User-Agent': CHROME_UA},
            timeout=15
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"  ✗ Failed to load date {date_str}: {e}")
        return True, []

    soup = BeautifulSoup(resp.text, 'html.parser')
    links = soup.find_all('a', href=re.compile(r'DisplayIncident\?incidentNumber=AK'))
    
    if not links:
        print(f"  No incident links found on {date_str}.")
        return True, []

    discovered = []
    seen_on_page = set()

    for link in links:
        href = link['href']
        inc_match = re.search(r'incidentNumber=(AK\d+)', href)
        if not inc_match:
            continue
        inc_id = inc_match.group(1)
        if inc_id in seen_on_page:
            continue
        seen_on_page.add(inc_id)
        
        h = generate_hash(inc_id)
        if h in existing_hashes:
            continue # already have it in the db

        # Ascend DOM to get the row text
        parent = link.find_parent(['li', 'div', 'tr', 'td'])
        if not parent:
            parent = link.parent
        for _ in range(4):
            if parent and len(parent.get_text(strip=True)) < 120:
                parent = parent.find_parent(['li', 'div', 'section'])
            else:
                break
        
        full_text = parent.get_text(separator='\n', strip=True) if parent else ''
        
        # Parse minimal fields to check condition
        location_m = re.search(r'Location[:\s]+([^\n]+)', full_text, re.I)
        type_m = re.search(r'Type[:\s]+([^\n]+)', full_text, re.I)
        dispatch_m = re.search(r'Dispatch Text[:\s]+([\s\S]+?)(?:Posted on|$)', full_text, re.I)
        
        location = location_m.group(1).strip() if location_m else 'Alaska'
        incident_type = type_m.group(1).strip() if type_m else 'Incident'
        dispatch_text = dispatch_m.group(1).strip() if dispatch_m else full_text[:600]
        
        title_str = f"AST {incident_type}: {location} [{inc_id}]"

        # Apply the Stolen Vehicle narrow filter to save compute cycles!
        if not is_stolen_vehicle(title_str, incident_type, " "): # only checking title/type to be fast, but we can check text too
             if not is_stolen_vehicle("", "", dispatch_text[:200]): # fast check top of text
                 continue

        print(f"    ⭐ STOLEN VEHICLE FOUND: {inc_id} ({location})")
        
        # Extract full data
        posted_m = re.search(r'Posted on ([^\n]+)', full_text, re.I)
        posted_raw = posted_m.group(1).strip() if posted_m else ''
        dispatch_text = re.sub(r'\s+', ' ', dispatch_text).strip()
        
        posted_ts = datetime.now(timezone.utc).isoformat()
        officer_id = None
        if posted_raw:
            officer_m = re.search(r'by\s+DPS\\+(.+?)$', posted_raw, re.I)
            if officer_m:
                officer_id = officer_m.group(1).strip()
            clean_posted = re.sub(r'\s+by\s+.*$', '', posted_raw, flags=re.I).strip()
            for fmt in ('%m/%d/%Y %I:%M:%S %p', '%m/%d/%Y %H:%M:%S', '%m/%d/%Y'):
                try:
                    posted_ts = datetime.strptime(clean_posted, fmt).replace(tzinfo=timezone.utc).isoformat()
                    break
                except ValueError:
                    continue
        
        entities = extract_entities(dispatch_text, incident_type)
        entities['detachment'] = 'General'
        entities['officer_id'] = officer_id
        
        region = infer_region(f"{location} {dispatch_text}")
        article_url = f"{BASE_URL}/Home/DisplayIncident?incidentNumber={inc_id}"
        
        # GEOCODE
        coords = None
        text_to_check = f"{entities.get('address_detail', '')} {dispatch_text}"
        mile_m = re.search(r'(?:near\s+)?Mile\s+([\d.]+)\s+(?:of\s+)?(?:the\s+)?([A-Z][a-zA-Z ]+(?:Highway|Hwy))', text_to_check, re.I)
        if mile_m:
            coords = geocode_milemarker(mile_m.group(2).strip(), float(mile_m.group(1)))
        if not coords:
            coords = geocode_text(f"{location} {dispatch_text}")

        item = {
            'hash':              h,
            'id':                inc_id,
            'source':            'Alaska State Troopers',
            'category':          'Safety',
            'title':             title_str,
            'link':              article_url,
            'sourceUrl':         BASE_URL,
            'articleUrl':        article_url,
            'lat':               coords[0] if coords else None,
            'lng':               coords[1] if coords else None,
            'favicon':           'https://www.dps.alaska.gov/favicon.ico',
            'location':          location,
            'incident_type':     incident_type,
            'summary':           dispatch_text[:800],
            'dataTag':           f"[Region: {region}] [Category: Law Enforcement]",
            'sourceAttribution': 'Source: Alaska State Troopers Daily Dispatch',
            'section':           'Safety',
            'sourceLean':        'neutral',
            'topic':             incident_type,
            'timestamp':         posted_ts,
            'scraped_at':        datetime.now(timezone.utc).isoformat(),
            'posted':            posted_raw,
            'entities':          entities,
        }
        discovered.append(item)

    return True, discovered

def run_deep_crawl(max_days=30):
    print("=" * 60)
    print("Starting Deep Stolen Vehicle Crawler (Daily Iteration)")
    print("=" * 60)
    
    existing = load_data()
    existing_hashes = {i.get('hash') for i in existing if i.get('hash')}
    print(f"Loaded {len(existing)} existing records from database.")
    
    new_vehicles = []
    current_date = datetime.now()
    
    for i in range(max_days):
        target_date = current_date - timedelta(days=i)
        has_content, discovered = process_date(target_date, existing_hashes)
        
        if discovered:
            new_vehicles.extend(discovered)
            for d in discovered:
                existing_hashes.add(d['hash'])
                
        # Be gentle to the server
        time.sleep(1.5)
        
    if new_vehicles:
        print(f"\nMerging {len(new_vehicles)} new historic stolen vehicles...")
        existing.extend(new_vehicles)
        
        # Sort chronologically by timestamp
        existing.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        save_data(existing)
        print("Data successfully committed.")
    else:
        print("\nNo new historic stolen vehicles discovered.")

if __name__ == "__main__":
    # Crawl backward for specified amount of days natively instead of generic pages
    run_deep_crawl(max_days=5)
