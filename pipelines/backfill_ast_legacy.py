#!/usr/bin/env python3
"""
Wayback Machine LEGACY Backfill Pipeline (2000-2019)
Queries archive.org for old DPS domains, downloads unstructured HTML,
and uses deep regex heuristics to synthesize structured intelligence.
"""

import sys
import os
import re
import json
import time
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup

# Import intelligence base functions
try:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from scrape_ast import (
        generate_hash, infer_region, FILE_PATH, load_data, save_data
    )
    from geo_dict import geocode_text
except ImportError:
    print("Run this script from alaskaintel-data/scripts")
    sys.exit(1)

CDX_API = "http://web.archive.org/cdx/search/cdx"

# Specific paths to avoid CDX 504 timeouts on the root domain
TARGET_PATHS = [
    "dps.state.ak.us/ast/pr/*",
    "dps.state.ak.us/ast/pio/pressreleases/*",
    "dps.state.ak.us/ast/dispatch/*",
    "dps.alaska.gov/ast/pio/pressreleases/*"
]

def get_legacy_manifest():
    manifest = []
    print("\n" + "=" * 60)
    print("Phase 1: CDX Legacy Registry Mapping")
    print("=" * 60)
    for path in TARGET_PATHS:
        print(f"[*] Querying CDX for {path}")
        params = {
            "url": path,
            "output": "json",
            "fl": "timestamp,original",
            "filter": ["statuscode:200", "mimetype:text/html"],
            "collapse": "timestamp:8" # Daily collapse
        }
        try:
            resp = requests.get(CDX_API, params=params, timeout=30)
            data = resp.json()
            if len(data) > 1:
                manifest.extend(data[1:])
                print(f"    -> Found {len(data)-1} snapshots")
        except Exception as e:
            print(f"    [!] Failed CDX query: {e}")
        time.sleep(2)
        
    print(f"\n[*] Total Unique Legacy Snapshots Queued: {len(manifest)}")
    return manifest

def extract_legacy_entities(text):
    """Heuristic fallback extraction for completely unstructured flat-text dispatches"""
    entities = {
        'suspects': [], 'charges': [], 'bac': None, 'facility': None,
        'bail': {'status': 'unknown', 'amount': None}, 'outcome': 'unknown',
        'incident_datetime': None, 'address_detail': None
    }
    
    # 1. Look for suspects
    for m in re.finditer(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s*,\s*(\d{2})\s*,\s*of\s+([A-Z][a-z]+)', text):
        entities['suspects'].append({'name': m.group(1), 'age': int(m.group(2))})
        if not entities['address_detail']: entities['address_detail'] = m.group(3)
        
    for m in re.finditer(r'arrested\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s*\(?(\d{2})?\)?', text):
        if not any(s['name'] == m.group(1) for s in entities['suspects']):
            entities['suspects'].append({'name': m.group(1), 'age': int(m.group(2)) if m.group(2) else None})

    # 2. Look for charges
    for m in re.finditer(r'(?:charges? of|remanded for|arrested for)\s+([^.!?]{5,100})', text, re.I):
        entities['charges'].append(m.group(1).strip())
        
    return entities

def parse_legacy_snapshot(timestamp, original_url, existing_hashes):
    archive_url = f"http://web.archive.org/web/{timestamp}id_/{original_url}"
    print(f"\n  -> Fetching Legacy [{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}]: {original_url}")
    
    try:
        resp = requests.get(archive_url, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"     [!] Connection failed: {e}")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # Legacy pages are often just <p> tags or <pre> tags containing the payload
    # We will grab all larger text blocks as potential incidents
    blocks = []
    for p in soup.find_all(['p', 'div', 'td', 'span']):
        txt = p.get_text(separator=' ', strip=True)
        if len(txt) > 200 and "Trooper" in txt:
            blocks.append(txt)
            
    # Pre-formatted legacy text
    for pre in soup.find_all('pre'):
        blocks.extend(pre.get_text().split('\n\n'))
        
    # Deduplicate
    blocks = list(set([re.sub(r'\s+', ' ', b).strip() for b in blocks if len(b.strip()) > 100]))
    
    if not blocks:
        print("     [-] No unstructured intelligence blocks found.")
        return []
        
    print(f"     [+] Found {len(blocks)} potential unstructured dispatches.")
    new_incidents = []
    
    for block in blocks:
        doc_hash = generate_hash(block)
        if doc_hash in existing_hashes: continue
        
        # Heuristically determine location
        location = "Alaska"
        loc_m = re.search(r'Location:\s*([^\n\.,]+)', block, re.I)
        if loc_m: location = loc_m.group(1).strip()
        
        # Heuristically determine type
        inc_type = "Legacy Incident"
        type_m = re.search(r'Type:\s*([^\n\.,]+)', block, re.I)
        if type_m: inc_type = type_m.group(1).strip()
        elif "DUI" in block: inc_type = "DUI"
        elif "Assault" in block: inc_type = "Assault"
        
        entities = extract_legacy_entities(block)
        region = infer_region(f"{location} {block}")
        
        # Date fallback
        try:
            posted_ts = datetime.strptime(timestamp[:8], '%Y%m%d').replace(tzinfo=timezone.utc).isoformat()
        except:
            posted_ts = datetime.now(timezone.utc).isoformat()
            
        coords = geocode_text(f"{location} {block}")
        
        item = {
            'hash':              doc_hash,
            'id':                f"LEGACY-{doc_hash[:8]}",
            'source':            'Alaska State Troopers',
            'category':          'Safety',
            'title':             f"AST {inc_type}: {location} (Archive)",
            'link':              archive_url,
            'sourceUrl':         'https://dps.state.ak.us',
            'articleUrl':        archive_url,
            'lat':               coords[0] if coords else None,
            'lng':               coords[1] if coords else None,
            'favicon':           'https://www.dps.alaska.gov/favicon.ico',
            'location':          location,
            'incident_type':     inc_type,
            'summary':           block[:800],
            'dataTag':           f"[Region: {region}] [Category: Law Enforcement]",
            'sourceAttribution': 'Source: AST Legacy Archives (2000-2019)',
            'section':           'Safety',
            'sourceLean':        'neutral',
            'topic':             inc_type,
            'timestamp':         posted_ts,
            'scraped_at':        datetime.now(timezone.utc).isoformat(),
            'posted':            f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}",
            'entities':          entities,
        }
        
        new_incidents.append(item)
        existing_hashes.add(doc_hash)
        
    print(f"     [+] Synthesized {len(new_incidents)} legacy records.")
    return new_incidents

def main():
    print("=" * 60)
    print("AST Legacy Unstructured Archive Mass Extractor (2000-2019)")
    print("=" * 60)
    
    manifest = get_legacy_manifest()
    if not manifest:
        print("No legacy targets found. Exiting.")
        sys.exit(0)
        
    db = load_data()
    existing_hashes = set([i['hash'] for i in db if 'hash' in i])
    print(f"\n[*] Loaded {len(existing_hashes)} records into checkpoint memory.")
    
    # Sort chronologically to walk upwards through time
    manifest.sort(key=lambda x: x[0])
    
    total_added = 0
    try:
        for timestamp, original_url in manifest:
            new_rows = parse_legacy_snapshot(timestamp, original_url, existing_hashes)
            if new_rows:
                db.extend(new_rows)
                total_added += len(new_rows)
                # Checkpoint
                print("     [»] Checkpointing legacy data to core database...")
                save_data(sorted(db, key=lambda x: x.get('timestamp', ''), reverse=True))
            time.sleep(1.5) # Mandatory archive API throttle
            
    except KeyboardInterrupt:
        print("\n\n[!] Script execution interrupted. Safely checkpointing legacy progress...")
        
    # Final save
    save_data(sorted(db, key=lambda x: x.get('timestamp', ''), reverse=True))
    print(f"\n✓ EXTRACTION PAUSED/COMPLETE")
    print(f"✓ Harvested {total_added} unstructured legacy records.")
    print("=" * 60)

if __name__ == "__main__":
    main()
