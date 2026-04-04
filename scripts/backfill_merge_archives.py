#!/usr/bin/env python3
import json
import os
import re
from datetime import datetime

def rebuild_master_archives():
    print("=" * 60)
    print("Master Archive Rebuild & Sync")
    print("=" * 60)
    
    # 1. Load all potential data sources
    sources = [
        'data/latest_intel.json',
        'data/adn_archive.json',
        'data/ast_logs.json',
        'data/stolen_vehicles.json'
    ]
    
    all_data = []
    for src in sources:
        if os.path.exists(src):
            print(f"[*] Loading {src}...")
            try:
                with open(src, 'r') as f:
                    data = json.load(f)
                    all_data.extend(data)
            except Exception as e:
                print(f"      [!] Failed: {e}")
                
    print(f"\n[*] Total raw signals loaded: {len(all_data)}")
    
    # 2. Group by YYYY/MM
    monthly_archives = {}
    for item in all_data:
        dt = item.get('timestamp')
        if not dt: continue
        match = re.search(r'^(\d{4})-(\d{2})', dt)
        if match:
            year, month = match.groups()
            key = f"{year}/{month}"
            if key not in monthly_archives:
                monthly_archives[key] = []
            monthly_archives[key].append(item)
            
    # 3. Process and Save
    os.makedirs('public/archive', exist_ok=True)
    manifest = []
    
    for key, items in monthly_archives.items():
        year, month = key.split('/')
        os.makedirs(f'public/archive/{year}', exist_ok=True)
        archive_path = f'public/archive/{year}/{month}.json'
        
        # Load existing archive to prevent data loss or to merge
        existing_archive = []
        if os.path.exists(archive_path):
            try:
                with open(archive_path, 'r') as af:
                    existing_archive = json.load(af)
            except Exception:
                pass
                
        # Merge and deduplicate by hash or link
        archive_dict = {}
        for x in existing_archive + items:
            h = x.get('hash') or x.get('link')
            if h:
                archive_dict[h] = x
            
        merged_items = sorted(list(archive_dict.values()), key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # Filter for the specific month (in case of overlap)
        final_items = [x for x in merged_items if x.get('timestamp', '').startswith(f"{year}-{month}")]
        
        with open(archive_path, 'w') as af:
            json.dump(final_items, af, indent=2)
            
        print(f"✓ Rebuilt {archive_path} ({len(final_items)} items)")
        manifest.append(key)
        
    # 4. Final Manifest
    with open('public/archive/manifest.json', 'w') as mf:
        json.dump(sorted(list(set(manifest)), reverse=True), mf, indent=2)
    print("\n✓ Manifest updated.")

if __name__ == "__main__":
    rebuild_master_archives()
