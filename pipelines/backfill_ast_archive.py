#!/usr/bin/env python3
"""
Wayback Machine Historical Backfill Pipeline for Alaska State Trooper Dispatches
Queries the archive.org CDX API for historical snapshots of the AST Daily Dispatch,
downloads the raw historical DOMs, and processes them through the standard NLP pipeline.
"""

import sys
import os
import re
import json
import time
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup

# Import intelligence extraction functions from the standard scraper
try:
    from scrape_ast import (
        extract_entities, generate_hash, infer_region, 
        FILE_PATH, load_data, save_data
    )
    from geo_dict import geocode_text
    from geo_milepost import geocode_milemarker
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Run this script from the alaskaintel-data/scripts directory.")
    sys.exit(1)

CDX_API = "http://web.archive.org/cdx/search/cdx"
target_url_pattern = "dailydispatch.dps.alaska.gov/Home/Display*"

def get_snapshot_manifest():
    """Retrieve all successful (HTTP 200) archived index pages."""
    print(f"[*] Querying CDX API for {target_url_pattern}...")
    params = {
        "url": target_url_pattern,
        "output": "json",
        "fl": "timestamp,original",
        "filter": "statuscode:200",
        "collapse": "timestamp:8" # Collapse to roughly one snapshot per day (YYYYMMDD) to prevent duplicate parsing
    }
    
    try:
        resp = requests.get(CDX_API, params=params, timeout=120)
        data = resp.json()
        if len(data) > 1:
            records = data[1:]
            # Filter specifically for the main Display index, ignore individual Incident routes right now
            index_records = [r for r in records if "DisplayIncident" not in r[1]]
            print(f"[*] Found {len(records)} total snapshots (Collapsed to daily).")
            print(f"[*] Deduped to {len(index_records)} primary index snapshots to traverse.")
            return index_records
        return []
    except Exception as e:
        print(f"[!] Failed to fetch CDX manifest: {e}")
        return []

def parse_archive_snapshot(timestamp, original_url, existing_hashes):
    """Fetch and parse a single raw archived DOM."""
    # The id_ suffix requests the raw document without Wayback UI
    archive_url = f"http://web.archive.org/web/{timestamp}id_/{original_url}"
    print(f"\n  -> Fetching Snapshot [{timestamp[:8]}]: {archive_url}")
    
    try:
        resp = requests.get(archive_url, timeout=20)
        # Wayback machine sometimes serves 200 headers with empty or broken dumps
        if resp.status_code != 200 or len(resp.text) < 500:
            print("     [-] Invalid or empty snapshot DOM.")
            return []
    except Exception as e:
        print(f"     [!] Connection failed: {e}")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    incident_links = soup.find_all('a', href=re.compile(r'DisplayIncident\?incidentNumber=AK'))
    
    if not incident_links:
        print("     [-] No dispatch links found in this DOM.")
        return []

    print(f"     [+] Found {len(incident_links)} dispatches on this page.")
    
    new_incidents = []
    
    for link in incident_links:
        try:
            inc_match = re.search(r'incidentNumber=(AK\d+)', link['href'])
            if not inc_match:
                continue
            inc_id = inc_match.group(1)
            
            # Skip if we already have it in db
            doc_hash = generate_hash(inc_id)
            if doc_hash in existing_hashes:
                continue
                
            # Content Extraction
            parent = link.find_parent(['li', 'div', 'tr', 'td'])
            if not parent: parent = link.parent
            for _ in range(4):
                if parent and len(parent.get_text(strip=True)) < 120:
                    parent = parent.find_parent(['li', 'div', 'section'])
                else:
                    break
                    
            full_text = parent.get_text(separator='\n', strip=True) if parent else ''
            
            # Extract basic metadata
            location_m = re.search(r'Location[:\s]+([^\n]+)', full_text, re.I)
            type_m = re.search(r'Type[:\s]+([^\n]+)', full_text, re.I)
            dispatch_m = re.search(r'Dispatch Text[:\s]+([\s\S]+?)(?:Posted on|$)', full_text, re.I)
            posted_m = re.search(r'Posted on ([^\n]+)', full_text, re.I)
            
            location = location_m.group(1).strip() if location_m else 'Alaska'
            incident_type = type_m.group(1).strip() if type_m else 'Incident'
            dispatch_text = dispatch_m.group(1).strip() if dispatch_m else full_text[:600]
            
            dispatch_text = re.sub(r'\s+', ' ', dispatch_text).strip()
            if not dispatch_text or len(dispatch_text) < 20:
                continue
                
            posted_raw = posted_m.group(1).strip() if posted_m else ''
            
            # Reconstruct timestamp
            posted_ts = None
            officer_id = None
            if posted_raw:
                officer_m = re.search(r'by\s+DPS\\+(.+?)$', posted_raw, re.I)
                if officer_m: officer_id = officer_m.group(1).strip()
                clean_posted = re.sub(r'\s+by\s+.*$', '', posted_raw, flags=re.I).strip()
                for fmt in ('%m/%d/%Y %I:%M:%S %p', '%m/%d/%Y %H:%M:%S', '%m/%d/%Y'):
                    try:
                        posted_ts = datetime.strptime(clean_posted, fmt).replace(tzinfo=timezone.utc).isoformat()
                        break
                    except ValueError: continue
            
            if not posted_ts:
                # If we can't parse the timestamp, fallback to the archive snapshot timestamp (YYYYMMDD)
                try:
                    posted_ts = datetime.strptime(timestamp[:8], '%Y%m%d').replace(tzinfo=timezone.utc).isoformat()
                except:
                    posted_ts = datetime.now(timezone.utc).isoformat()
            
            # Apply Deep NLP Extraction
            entities = extract_entities(dispatch_text, incident_type)
            entities['officer_id'] = officer_id
            
            region = infer_region(f"{location} {dispatch_text}")
            title = f"AST {incident_type}: {location} [{inc_id}]"
            article_url = f"https://dailydispatch.dps.alaska.gov/Home/DisplayIncident?incidentNumber={inc_id}"
            
            # Execute Geocoding
            coords = None
            text_to_check = f"{entities.get('address_detail', '')} {dispatch_text}"
            mile_m = re.search(r'(?:near\s+)?Mile\s+([\d.]+)\s+(?:of\s+)?(?:the\s+)?([A-Z][a-zA-Z ]+(?:Highway|Hwy))', text_to_check, re.I)
            if mile_m:
                coords = geocode_milemarker(mile_m.group(2).strip(), float(mile_m.group(1)))
            if not coords:
                coords = geocode_text(f"{location} {dispatch_text}")
            
            item = {
                'hash':              doc_hash,
                'id':                inc_id,
                'source':            'Alaska State Troopers',
                'category':          'Safety',
                'title':             title,
                'link':              article_url,
                'sourceUrl':         'https://dailydispatch.dps.alaska.gov',
                'articleUrl':        article_url,
                'lat':               coords[0] if coords else None,
                'lng':               coords[1] if coords else None,
                'favicon':           'https://www.dps.alaska.gov/favicon.ico',
                'location':          location,
                'incident_type':     incident_type,
                'summary':           dispatch_text[:800],
                'dataTag':           f"[Region: {region}] [Category: Law Enforcement]",
                'sourceAttribution': 'Source: Alaska State Troopers Historical Archive',
                'section':           'Safety',
                'sourceLean':        'neutral',
                'topic':             incident_type,
                'timestamp':         posted_ts,
                'scraped_at':        datetime.now(timezone.utc).isoformat(),
                'posted':            posted_raw,
                'entities':          entities,
            }
            
            new_incidents.append(item)
            existing_hashes.add(doc_hash)
            
        except Exception as e:
            print(f"     [!] Failed to parse incident: {e}")
            continue
            
    print(f"     [+] Successfully extracted {len(new_incidents)} NEW historical records.")
    return new_incidents

def main():
    print("=" * 60)
    print("AST Historical Archive Mass Extractor")
    print("=" * 60)
    
    manifest = get_snapshot_manifest()
    if not manifest:
        print("No snapshots found. Exiting.")
        sys.exit(0)
        
    db = load_data()
    existing_hashes = set([i['hash'] for i in db if 'hash' in i])
    print(f"[*] Loaded initial database with {len(existing_hashes)} distinct records.")
    
    total_added = 0
    # Process oldest first to build forwards chronologically
    manifest.sort(key=lambda x: x[0])
    
    try:
        for idx, (timestamp, original_url) in enumerate(manifest):
            new_rows = parse_archive_snapshot(timestamp, original_url, existing_hashes)
            
            if new_rows:
                db.extend(new_rows)
                total_added += len(new_rows)
                
                # Checkpoint save every batch to ensure we don't lose data on crash
                print("     [»] Checkpointing database to disk...")
                db_sorted = sorted(db, key=lambda x: x.get('timestamp', ''), reverse=True)
                save_data(db_sorted)
                
            # Polite wait to avoid archive.org ratelimiting
            time.sleep(1.5)
            
    except KeyboardInterrupt:
        print("\n\n[!] Script interrupted by operator. Saving progress...")
    
    db_sorted = sorted(db, key=lambda x: x.get('timestamp', ''), reverse=True)
    save_data(db_sorted)
    
    print("\n" + "=" * 60)
    print(f"✓ EXTRACTION COMPLETE / HALTED")
    print(f"✓ Total new historical records extracted: {total_added}")
    print(f"✓ Total finalized database size: {len(db_sorted)}")
    print("=" * 60)

if __name__ == "__main__":
    main()
