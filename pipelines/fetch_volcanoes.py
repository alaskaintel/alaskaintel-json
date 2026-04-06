#!/usr/bin/env python3
"""
fetch_volcanoes.py — Alaska Volcano Observatory Fetcher
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fetches active volcano status and notices from the USGS Volcano API.
Filters specifically for AVO (Alaska Volcano Observatory) and HVO if needed.
Maps Aviation Color Codes and Alert Levels to AlaskaIntel impact scores.
"""

import json
import os
import hashlib
import requests
from datetime import datetime, timezone

USGS_API_URL = "https://volcanoes.usgs.gov/hans-public/api/vns/notices"
INGEST_URL = "https://api01.alaskaintel.com/ingest"
INGEST_SECRET = os.environ.get("INGEST_SECRET", "")

CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"

IMPACT_MAP = {
    "RED": 95,
    "WARNING": 90,
    "ORANGE": 75,
    "WATCH": 70,
    "YELLOW": 45,
    "ADVISORY": 40,
    "GREEN": 10,
    "NORMAL": 10,
    "UNASSIGNED": 10
}

def make_hash(notice_id: str) -> str:
    return "avo-" + hashlib.md5(str(notice_id).encode()).hexdigest()

def notice_to_signal(notice: dict) -> dict:
    """Convert USGS Notice to AlaskaIntel signal."""
    # AVO notices only
    obs = notice.get("observatory", "")
    if obs != "AVO":
        # We only want Alaska, not Hawaii (HVO) or Cascades (CVO)
        return None
        
    notice_id = notice.get("noticeNumber", "")
    volcano = notice.get("volcanoName", "Unknown Volcano")
    content = notice.get("content", "")
    level = notice.get("alertLevel", "UNASSIGNED").upper()
    color = notice.get("aviationColorCode", "UNASSIGNED").upper()
    
    # Skip Green/Normal updates to reduce noise, unless it's a downgrade we just received
    if color == "GREEN" and level == "NORMAL":
        return None

    issued = notice.get("issuedTime", "")
    ts = datetime.now(timezone.utc).isoformat()
    if issued:
        try:
            ts = datetime.fromisoformat(issued.replace("Z", "+00:00")).isoformat()
        except:
            pass

    # Extract coordinates from nested volcano array if present
    lat, lng = None, None
    volc_data = notice.get("volcanoes", [])
    if volc_data and len(volc_data) > 0:
        lat = volc_data[0].get("latitude")
        lng = volc_data[0].get("longitude")

    title = f"🌋 {volcano}: Color Code {color}"
    
    # Strip HTML from content if present
    import re
    clean_content = re.sub(r"<[^>]+>", " ", content).strip()
    clean_content = re.sub(r"\s+", " ", clean_content)[:400] + "..."
    
    score = max(IMPACT_MAP.get(color, 20), IMPACT_MAP.get(level, 20))
    urgency = "now" if score >= 70 else "background"
    
    signal_id = make_hash(notice_id)
    article_url = f"https://avo.alaska.edu/activity/{volcano.replace(' ', '')}"
    
    signal = {
        "id":               signal_id,
        "hash":             signal_id,
        "title":            title,
        "summary":          clean_content,
        "source":           "Alaska Volcano Observatory",
        "articleUrl":       article_url,
        "sourceUrl":        "https://avo.alaska.edu/",
        "timestamp":        ts,
        "dataTag":          f"[Aviation Color: {color}] [Alert Level: {level}]",
        "sourceAttribution":"Source: USGS / AVO Notice",
        "impactScore":      score,
        "region":           "Aleutians / Gulf", # Many AVO are Aleutians
        "sector":           "emergency",
        "urgency":          urgency,
        "topic":            "volcano",
        "favicon":          "https://avo.alaska.edu/favicon.ico",
    }
    
    if lat and lng:
        signal["lat"] = float(lat)
        signal["lng"] = float(lng)
        
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
        print(f"  ✓ Ingested {len(signals)} AVO Volcano signals → D1")
    except Exception as e:
        print(f"  ✗ Failed to POST AVO signals: {e}")

def main():
    print("=" * 60)
    print("Alaska Volcano Observatory (AVO) Fetcher")
    print("=" * 60)
    
    try:
        resp = requests.get(USGS_API_URL, headers={"User-Agent": CHROME_UA}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"✗ Error fetching USGS API: {e}")
        return
        
    notices = data if isinstance(data, list) else data.get("notices", [])
    print(f"  Retrieved {len(notices)} total notices from USGS")
    
    signals = []
    for n in notices[:50]: # Look at recent 50
        sig = notice_to_signal(n)
        if sig:
            signals.append(sig)
            
    print(f"  Filtered to {len(signals)} actionable AVO alerts.")
    
    if signals:
        os.makedirs("data", exist_ok=True)
        with open("data/volcanoes.json", "w") as f:
            json.dump(signals, f, indent=2)
        post_signals(signals)

if __name__ == "__main__":
    main()
