#!/usr/bin/env python3
"""
Alaska Fire Service (AFS) Active Fires Scraper
Fetches active fire points from the BLM ArcGIS Feature Server and converts them to the AlaskaIntel signal format.
"""

import json
import os
import requests
from datetime import datetime, timezone

# ArcGIS REST API Endpoint for Current Year Fire Points
AFS_FIRES_URL = "https://fire.ak.blm.gov/arcgis/rest/services/MapAndFeatureServices/CurrentFirePoints/FeatureServer/6/query"

# Output file
OUTPUT_FILE = os.path.join("data", "afs_fires.json")

def fetch_and_parse_fires():
    params = {
        "where": "1=1",
        "outFields": "*",
        "f": "geojson",
        "returnGeometry": "true"
    }

    print("Fetching active fires from Alaska Fire Service ArcGIS endpoint...")
    try:
        response = requests.get(AFS_FIRES_URL, params=params, verify=False, timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Error fetching AFS fires: {e}")
        return

    features = data.get("features", [])
    print(f"Found {len(features)} total fires.")

    signals = []
    
    for feature in features:
        props = feature.get("properties", {})
        geometry = feature.get("geometry")

        # Skip if missing name
        if not props.get("NAME"):
            continue

        # Extract fields
        incident_name = props.get("NAME", "Unknown Fire")
        incident_num = props.get("RECORDNUMBER", props.get("OBJECTID", "Unknown"))
        acres = props.get("ESTIMATEDTOTALACRES", props.get("IASIZE", 0.0))
        
        # Format dates (ArcGIS returns unix epoch in milliseconds)
        discovery_ms = props.get("DISCOVERYDATETIME")
        published_iso = datetime.now(timezone.utc).isoformat()
        if discovery_ms:
            try:
                published_iso = datetime.fromtimestamp(discovery_ms / 1000.0, tz=timezone.utc).isoformat()
            except:
                pass

        out_date_ms = props.get("OUTDATE")
        status = props.get("STATUS", "Active")
        
        # Do not include fires that are already out completely (unless very recent)
        if status == "Out":
            try:
                out_date = datetime.fromtimestamp(out_date_ms / 1000.0, tz=timezone.utc)
                if (datetime.now(timezone.utc) - out_date).days > 7:
                    continue # Skip fires out for more than 7 days
            except:
                pass


        cause = props.get("GENERALCAUSE", "Unknown Cause")
        owner = props.get("ORIGINOWNERID", props.get("OWNERKIND", "Unknown Owner"))
        area = props.get("MGMTOFFICEID", props.get("MGMTORGID", ""))

        title = f"{incident_name} Fire ({acres} acres)"
        
        summary = f"Status: {status} | Area: {area} | Cause: {cause} | Owner: {owner}"
        
        # Link to the general intel page or the generic AFS dashboard
        # AICC Situation Report Dashboard
        link = "https://www.arcgis.com/apps/dashboards/71b0377b3c3d4f719e11b8caa50fb529"

        # Unique hash
        import hashlib
        hash_str = hashlib.md5(f"afs_fire_{incident_num}_{title}".encode()).hexdigest()

        signal = {
            "title": title,
            "link": link,
            "published": published_iso,
            "source": "Alaska Fire Service",
            "category": "Emergency",
            "summary": summary,
            "hash": hash_str,
            "type": "fire"
        }

        # Add location if exists
        if geometry and "coordinates" in geometry:
            coords = geometry["coordinates"]
            if len(coords) == 2:
                signal["location"] = {
                    "lon": coords[0],
                    "lat": coords[1]
                }

        signals.append(signal)

    print(f"Parsed {len(signals)} active/recent fires into signals.")

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(signals, f, indent=4)
        
    print(f"Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    fetch_and_parse_fires()
