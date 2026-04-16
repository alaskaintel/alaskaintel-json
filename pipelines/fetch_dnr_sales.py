#!/usr/bin/env python3
import requests
import json
import os
import hashlib
from datetime import datetime, timezone

URL = "https://arcgis.dnr.alaska.gov/arcgis/rest/services/OpenData/LandActivity_ResourceSale/FeatureServer/1/query?where=1=1&outFields=*&f=geojson&resultRecordCount=2000"

def generate_hash(title: str, link: str) -> str:
    unique_string = f"{title}|{link}"
    return hashlib.md5(unique_string.encode()).hexdigest()

def run():
    print("Fetching DNR Resource Sales...")
    # Proxied layer bypass
    proxy_url = "https://alaskaintel-api.kbdesignphoto.workers.dev/dnr/land-sales?v=2"
    headers = {"User-Agent": "AlaskaIntel/1.0 (data.alaskaintel.com)"}
    
    resp = requests.get(proxy_url, headers=headers, timeout=20)
    if not resp.ok:
        print(f"Proxy failed HTTP {resp.status_code}. Falling back to direct ArcGIS...")
        resp = requests.get(URL, headers=headers, timeout=30)
        
    if not resp.ok:
        print(f"Failed to fetch DNR GeoJSON upstream: {resp.status_code}")
        return

    try:
        data = resp.json()
    except Exception as e:
        print(f"Failed to parse JSON: {e}")
        return
        
    features = data.get("features", [])
    print(f"Found {len(features)} total land sale features.")

    # Target path inside intel-json/data/land_sales/
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data", "land_sales")
    os.makedirs(data_dir, exist_ok=True)
    intel_path = os.path.join(data_dir, "latest_landsales.json")

    intel_data = []
    if os.path.exists(intel_path):
        with open(intel_path, "r") as f:
            try:
                intel_data = json.load(f)
            except:
                pass

    existing_hashes = {item.get("hash") for item in intel_data if "hash" in item}

    now_iso = datetime.now(timezone.utc).isoformat()
    extracted = []
    
    for f in features:
        props = f.get("properties", {})
        case_id = props.get("CASE_ID") or props.get("FILENUMBER")
        if not case_id: continue
        
        status = props.get('CSSTTSDSCR', 'Unknown').upper()
        if "CLOSED" in status or "EXPIRED" in status or "REJECTED" in status:
            continue
            
        title = f"[DNR Resource Sale] {props.get('CSTMRNM', 'Notice')}"
        info_link = props.get("INFO_LINK") or "https://dnr.alaska.gov/mlw/landsales/"
        
        h = generate_hash(title, info_link)
        if h in existing_hashes:
            continue
            
        category = props.get('CSTYPDSCRP', 'Resource Sale')
        summary = f"File: {case_id} | Status: {status} | Type: {category}"
        
        geom = f.get("geometry")
        lat = lng = None
        if geom and geom.get("type") == "Point":
            lng, lat = geom["coordinates"]
        elif geom and geom.get("type") == "Polygon":
            try:
                lng, lat = geom["coordinates"][0][0]
            except Exception:
                pass
                
        sig = {
            "id": f"dnr-sale-{h}",
            "hash": h,
            "title": title,
            "summary": summary,
            "source": "AK Dept of Natural Resources",
            "articleUrl": info_link,
            "sourceUrl": "https://dnr.alaska.gov",
            "timestamp": now_iso, 
            "dataTag": "[Land Sales]",
            "region": "Statewide",
            "topic": "economy",
            "section": "infrastructure",
            "lat": lat,
            "lng": lng
        }
        extracted.append(sig)

    # First run clamping bounds
    extracted = extracted[:10]
    print(f"Extracted {len(extracted)} net-new resource sales.")
    
    # We must unconditionally write if there are new extractions OR if the file doesn't exist
    if extracted or not os.path.exists(intel_path):
        intel_data = extracted + intel_data
        intel_data = intel_data[:500] 
        
        with open(intel_path, "w") as f:
            json.dump(intel_data, f, indent=2)

if __name__ == "__main__":
    run()
