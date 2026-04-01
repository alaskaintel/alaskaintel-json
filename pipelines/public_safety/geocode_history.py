"""
Script to loop through existing data/ast_logs.json and apply the new geocoding
logic to historical incidents that lack lat/lng.
"""

import json
import re
import os
from datetime import datetime, timezone
import sys

# Ensure imports from current directory work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from geo_dict import geocode_text
from geo_milepost import geocode_milemarker

FILE_PATH = '../data/ast_logs.json'

def main():
    if not os.path.exists(FILE_PATH):
        print(f"File not found: {FILE_PATH}")
        return

    with open(FILE_PATH, 'r') as f:
        incidents = json.load(f)

    updated_count = 0
    skipped_count = 0

    print(f"Loaded {len(incidents)} incidents. Scanning for un-geocoded entries...")

    for item in incidents:
        # If already has lat/lng natively, skip
        if item.get('lat') is not None and item.get('lng') is not None:
            skipped_count += 1
            continue

        # Start geocoding logic from scrape_ast.py
        dispatch_text = item.get('summary', '')
        location = item.get('location', 'Alaska')
        entities = item.get('entities', {})
        
        coords = None
        
        # 1. Check for mile marker
        text_to_check = f"{entities.get('address_detail', '')} {dispatch_text}"
        mile_m = re.search(r'(?:near\s+)?Mile\s+([\d.]+)\s+(?:of\s+)?(?:the\s+)?([A-Z][a-zA-Z ]+(?:Highway|Hwy))', text_to_check, re.I)
        if mile_m:
            coords = geocode_milemarker(mile_m.group(2).strip(), float(mile_m.group(1)))
            if coords:
                print(f"  [GEO_MILEPOST] matched '{mile_m.group(0)}' -> {coords}")

        # 2. Fall back to text
        if not coords:
            coords = geocode_text(f"{location} {dispatch_text}")

        # Apply
        if coords:
            item['lat'] = coords[0]
            item['lng'] = coords[1]
            updated_count += 1
        else:
            # Explicitly mark as null if geocoding yields nothing
            item['lat'] = None
            item['lng'] = None

    print(f"Geocoded {updated_count} new entries. Skipped {skipped_count} existing entries.")

    with open(FILE_PATH, 'w') as f:
        json.dump(incidents, f, indent=2)
    print("Saved to", FILE_PATH)

if __name__ == "__main__":
    main()
