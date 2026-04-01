#!/usr/bin/env python3
"""
fetch_nws_cap.py — NWS Alaska CAP Alerts Fetcher
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fetches active weather alerts for Alaska from the NWS JSON API.
Extracts critical CAP elements: severity, certainty, polygons.
Replaces the standard RSS fetch which strips this data out.
"""

import json
import os
import hashlib
import requests
from datetime import datetime, timezone

# ── Config ───────────────────────────────────────────────────────────────────
NWS_ALERTS_URL = "https://api.weather.gov/alerts/active?area=AK"
INGEST_URL = "https://alaskaintel-api.kbdesignphoto.workers.dev/ingest"
INGEST_SECRET = os.environ.get("INGEST_SECRET", "")

# We need a custom user agent per NWS API requirements
NWS_UA = "AlaskaIntel-Pipeline/1.0 (admin@alaskaintel.com)"

# NWS Severity -> AlaskaIntel Impact Score
IMPACT_MAP = {
    "Extreme": 100,
    "Severe": 80,
    "Moderate": 50,
    "Minor": 20,
    "Unknown": 30
}

# NWS Urgency -> AlaskaIntel Urgency
URGENCY_MAP = {
    "Immediate": "now",
    "Expected": "now",
    "Future": "background",
    "Past": "background",
    "Unknown": "background"
}


def make_hash(event_id: str) -> str:
    """Stable deduplication ID from NWS ID."""
    return "nws-cap-" + hashlib.md5(event_id.encode()).hexdigest()

def extract_centroid(geometry: dict) -> tuple:
    """Extract a rough centroid from a GeoJSON polygon to drop a pin."""
    if not geometry or geometry.get("type") != "Polygon":
        return None, None
    coords = geometry.get("coordinates")
    if not coords or len(coords) == 0:
        return None, None
    
    # Outer ring
    ring = coords[0]
    lat_sum = 0
    lng_sum = 0
    count = len(ring)
    for lng, lat in ring:
        lat_sum += lat
        lng_sum += lng
    
    return lat_sum / count, lng_sum / count

def event_to_signal(feature: dict) -> dict:
    """Convert an NWS GeoJSON Feature into an AlaskaIntel signal dict."""
    props = feature.get("properties", {})
    geom = feature.get("geometry", {})
    
    ext_id = props.get("id", "")
    title = props.get("headline", props.get("event", "NWS Weather Alert"))
    summary = props.get("description", "")
    instruction = props.get("instruction", "")
    
    severity = props.get("severity", "Unknown")
    nws_urgency = props.get("urgency", "Unknown")
    
    # Ignore minor advisories like "Small Craft Advisory" to reduce noise
    event_type = props.get("event", "")
    if event_type in ["Small Craft Advisory", "Special Weather Statement"] and severity in ["Minor", "Moderate"]:
        return None
        
    full_desc = f"{summary}\n{instruction}".strip()
    if len(full_desc) > 400:
        full_desc = full_desc[:397] + "..."
        
    lat, lng = extract_centroid(geom)
    impact = IMPACT_MAP.get(severity, 40)
    urgency = URGENCY_MAP.get(nws_urgency, "background")
    
    region = props.get("areaDesc", "Statewide")
    if len(region) > 50: # If it's a massive list of zones, just call it Statewide
        region = "Statewide"
        
    signal_id = make_hash(ext_id)
    
    signal = {
        "id":               signal_id,
        "hash":             signal_id,
        "title":            f"🚨 NWS {severity}: {event_type}",
        "summary":          full_desc,
        "source":           "NWS Alaska",
        "articleUrl":       f"https://alerts.weather.gov/search?query={ext_id}",
        "sourceUrl":        "https://www.weather.gov/alaska/",
        "timestamp":        props.get("sent", datetime.now(timezone.utc).isoformat()),
        "dataTag":          f"[Region: {region}] [Severity: {severity}]",
        "sourceAttribution":"Source: National Weather Service CAP Feed",
        "impactScore":      impact,
        "region":           region,
        "sector":           "weather",
        "urgency":          urgency,
        "topic":            event_type,
        "favicon":          "https://www.weather.gov/favicon.ico",
    }
    
    if lat is not None and lng is not None:
        signal["lat"] = lat
        signal["lng"] = lng
        
    return signal

def post_signals(signals: list) -> None:
    if not signals:
        return

    headers = {"Content-Type": "application/json"}
    if INGEST_SECRET:
        headers["Authorization"] = f"Bearer {INGEST_SECRET}"

    try:
        resp = requests.post(INGEST_URL, json=signals, headers=headers, timeout=30)
        resp.raise_for_status()
        res = resp.json()
        print(f"  ✓ Ingested {res.get('inserted', len(signals))} NWS CAP signals → D1")
    except Exception as e:
        print(f"  ✗ Failed to POST NWS CAP signals: {e}")

def main():
    print("=" * 60)
    print("NWS Alaska CAP Alerts Fetcher")
    print("=" * 60)
    
    try:
        resp = requests.get(NWS_ALERTS_URL, headers={"User-Agent": NWS_UA}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"✗ Error fetching NWS API: {e}")
        return
        
    features = data.get("features", [])
    print(f"  Retrieved {len(features)} total alerts from NWS AK")
    
    signals = []
    for f in features:
        sig = event_to_signal(f)
        if sig:
            signals.append(sig)
            
    print(f"  Filtered to {len(signals)} actionable high-severity alerts.")
    
    if signals:
        os.makedirs("data", exist_ok=True)
        with open("data/nws_cap.json", "w") as f:
            json.dump(signals, f, indent=2)
        post_signals(signals)

if __name__ == "__main__":
    main()
