#!/usr/bin/env python3
"""
fetch_511ak.py — Alaska 511 Road Events Fetcher
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Calls the 511.alaska.gov REST API (v2) to pull real-time road events:
  • Construction / roadwork zones
  • Full closures
  • Accidents & incidents

Each event comes with real lat/lng from the API — no centroid fallback needed.
Events are mapped to AlaskaIntel signals and POSTed to the /ingest endpoint.

SETUP:
  1. Sign up for a free API key at https://511.alaska.gov/
  2. Set env var:  export AK511_API_KEY=your_key_here
     Or add to GitHub Actions secrets: AK511_API_KEY

USAGE:
  python scripts/fetch_511ak.py              # normal run
  python scripts/fetch_511ak.py --dry-run    # print events, no POST
"""

import hashlib
import json
import os
import sys
import argparse
import requests
from datetime import datetime, timezone

# ── Config ───────────────────────────────────────────────────────────────────

API_BASE   = "https://511.alaska.gov/api/v2/get"
API_KEY    = os.environ.get("AK511_API_KEY", "")
INGEST_URL = "https://alaskaintel-api.kbdesignphoto.workers.dev/ingest"
INGEST_SECRET = os.environ.get("INGEST_SECRET", "")

# Event types to include. 511AK uses these strings in the `type` field.
INCLUDE_TYPES = {
    "roadwork",
    "construction",
    "closures",
    "closure",
    "accidentsandincidents",
    "accidentsAndIncidents",
    "incident",
}

# Urgency mapping by event type
URGENCY_MAP = {
    "closures":              "now",
    "closure":               "now",
    "accidentsandincidents": "now",
    "accidentsAndIncidents": "now",
    "incident":              "now",
    "roadwork":              "background",
    "construction":          "background",
}

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_id(event: dict) -> str:
    """Stable deduplication ID from the 511 event ID."""
    raw = str(event.get("id") or event.get("ID") or json.dumps(event, sort_keys=True))
    return "ak511-" + hashlib.md5(raw.encode()).hexdigest()


def infer_region(text: str) -> str:
    """Simple keyword → region mapping for 511 events."""
    text = (text or "").lower()
    if any(k in text for k in ["anchorage", "muldoon", "tudor", "dimond", "seward hwy"]):
        return "Southcentral"
    if any(k in text for k in ["fairbanks", "north pole", "delta", "tok"]):
        return "Interior"
    if any(k in text for k in ["juneau", "sitka", "ketchikan", "wrangell", "petersburg"]):
        return "Southeast"
    if any(k in text for k in ["matanuska", "wasilla", "palmer", "mat-su", "willow"]):
        return "Mat-Su"
    if any(k in text for k in ["kenai", "soldotna", "homer", "kachemak"]):
        return "Southcentral"
    if any(k in text for k in ["kodiak", "valdez", "cordova", "seward"]):
        return "Gulf Coast"
    if any(k in text for k in ["bethel", "nome", "dillingham", "yukon"]):
        return "Yukon-Kuskokwim"
    if any(k in text for k in ["barrow", "utqia", "north slope", "prudhoe"]):
        return "North Slope"
    return "Statewide"


def event_to_signal(event: dict) -> dict:
    """Convert a 511AK event dict to an AlaskaIntel signal dict."""
    etype      = (event.get("type") or event.get("eventType") or "roadwork").lower().replace(" ", "")
    roadway    = event.get("roadwayName") or event.get("road") or "Alaska Road"
    direction  = event.get("directionOfTravel") or event.get("direction") or ""
    desc       = event.get("description") or event.get("headline") or f"Road event on {roadway}"
    title      = f"🚧 {roadway}{' ' + direction if direction else ''}: {desc[:80]}"

    # Coordinates — 511AK provides these on the event object
    lat = event.get("latitude") or event.get("lat") or \
          (event.get("geography", {}) or {}).get("lat")
    lng = event.get("longitude") or event.get("lng") or event.get("lon") or \
          (event.get("geography", {}) or {}).get("lon")

    # Try nested startPoint if top-level coords missing
    if lat is None and event.get("startPoint"):
        lat = event["startPoint"].get("latitude") or event["startPoint"].get("lat")
        lng = event["startPoint"].get("longitude") or event["startPoint"].get("lon")

    try:
        lat = float(lat) if lat is not None else None
        lng = float(lng) if lng is not None else None
    except (TypeError, ValueError):
        lat = lng = None

    # Timestamp — prefer reported, fall back to lastUpdated or now
    reported = event.get("reported") or event.get("startDate") or event.get("created")
    ts = datetime.now(timezone.utc).isoformat()
    if reported:
        try:
            ts = datetime.fromisoformat(reported.replace("Z", "+00:00")).isoformat()
        except Exception:
            pass

    planned_end = event.get("plannedEndDate") or event.get("estimatedEnd") or ""

    urgency      = URGENCY_MAP.get(etype, "background")
    region       = infer_region(f"{roadway} {desc}")
    impact_score = 70 if urgency == "now" else 40
    signal_id    = make_id(event)

    summary = desc
    if planned_end:
        summary += f" Estimated clearance: {planned_end}."

    # Cap summary at 300 chars
    if len(summary) > 300:
        summary = summary[:297].rstrip() + "..."

    signal: dict = {
        "id":               signal_id,
        "title":            title[:200],
        "summary":          summary,
        "source":           "Alaska 511",
        "articleUrl":       f"https://511.alaska.gov/map#event/{event.get('id', '')}",
        "sourceUrl":        "https://511.alaska.gov",
        "timestamp":        ts,
        "dataTag":          f"[Region: {region}] [Category: Transportation]",
        "sourceAttribution":"Source: Alaska 511 Road Conditions",
        "impactScore":      impact_score,
        "region":           region,
        "sector":           "transportation",
        "urgency":          urgency,
        "topic":            "transportation",
        "favicon":          "https://511.alaska.gov/favicon.ico",
    }

    if lat is not None and lng is not None:
        signal["lat"] = lat
        signal["lng"] = lng

    return signal


def camera_to_signal(cam: dict) -> dict:
    """Convert a 511AK camera dict to an AlaskaIntel signal dict."""
    title      = f"📷 RWIS Camera: {cam.get('name') or 'Traffic Camera'}"
    desc       = cam.get("description") or "Live camera feed from Road Weather Information System."
    
    lat = cam.get("latitude") or (cam.get("geography", {}) or {}).get("lat")
    lng = cam.get("longitude") or (cam.get("geography", {}) or {}).get("lon")
    try:
        lat = float(lat) if lat is not None else None
        lng = float(lng) if lng is not None else None
    except (TypeError, ValueError):
        lat = lng = None

    region = infer_region(f"{title} {desc}")
    signal_id = "ak511-cam-" + hashlib.md5(str(cam.get('id') or title).encode()).hexdigest()

    # Attempt to extract image URL from camera view(s)
    image_url = None
    views = cam.get("views", [])
    if views and isinstance(views, list) and len(views) > 0:
        image_url = views[0].get("url")

    signal: dict = {
        "id":               signal_id,
        "title":            title[:200],
        "summary":          desc,
        "source":           "Alaska 511 Cameras",
        "articleUrl":       f"https://511.alaska.gov/map#camera/{cam.get('id', '')}",
        "sourceUrl":        "https://511.alaska.gov",
        "timestamp":        datetime.now(timezone.utc).isoformat(),
        "dataTag":          f"[Region: {region}] [Category: Weather/Cameras]",
        "sourceAttribution":"Source: Alaska 511 RWIS Cameras",
        "impactScore":      40,
        "region":           region,
        "sector":           "weather",
        "urgency":          "background",
        "topic":            "weather",
        "favicon":          "https://511.alaska.gov/favicon.ico",
    }

    if image_url:
        signal["imageUrl"] = image_url

    if lat is not None and lng is not None:
        signal["lat"] = lat
        signal["lng"] = lng

    return signal


# ── Main fetch ────────────────────────────────────────────────────────────────

def fetch_511ak_events() -> list:
    """Fetch all current road events from 511AK API."""
    if not API_KEY:
        print("⚠  AK511_API_KEY not set — skipping 511AK fetch.")
        print("   Sign up at https://511.alaska.gov/ to get a free key.")
        return []

    url    = f"{API_BASE}/event"
    params = {"format": "json", "key": API_KEY}

    print(f"Fetching 511AK events from {url}...")
    try:
        resp = requests.get(url, params=params, headers={"User-Agent": CHROME_UA}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"✗ Error fetching 511AK events: {e}")
        return []

    events = data if isinstance(data, list) else data.get("events", data.get("features", []))
    print(f"  Retrieved {len(events)} total events from 511AK")
    return events


def fetch_511ak_cameras() -> list:
    """Fetch all RWIS cameras from 511AK API."""
    if not API_KEY:
        return []

    url    = f"{API_BASE}/cameras"
    params = {"format": "json", "key": API_KEY}

    print(f"Fetching 511AK cameras from {url}...")
    try:
        resp = requests.get(url, params=params, headers={"User-Agent": CHROME_UA}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"✗ Error fetching 511AK cameras: {e}")
        return []

    cams = data if isinstance(data, list) else data.get("cameras", data.get("features", []))
    print(f"  Retrieved {len(cams)} total cameras from 511AK")
    return cams


def filter_events(events: list) -> list:
    """Keep only road construction, closures, and active incidents."""
    kept = []
    for ev in events:
        etype = (ev.get("type") or ev.get("eventType") or "").lower().replace(" ", "")
        if any(t in etype for t in INCLUDE_TYPES):
            kept.append(ev)
    print(f"  Filtered to {len(kept)} relevant events (roadwork/closures/incidents)")
    return kept


def post_signals(signals: list) -> None:
    """POST signals to the AlaskaIntel ingest endpoint."""
    if not signals:
        print("  No signals to POST.")
        return

    headers = {"Content-Type": "application/json"}
    if INGEST_SECRET:
        headers["Authorization"] = f"Bearer {INGEST_SECRET}"

    try:
        resp = requests.post(INGEST_URL, json=signals, headers=headers, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        print(f"  ✓ Ingested {result.get('inserted', len(signals))} 511AK signals → D1")
    except Exception as e:
        print(f"  ✗ Failed to POST signals: {e}")


def main():
    parser = argparse.ArgumentParser(description="Fetch 511AK road events and ingest to AlaskaIntel")
    parser.add_argument("--dry-run", action="store_true", help="Print signals without POSTing")
    args = parser.parse_args()

    print("=" * 60)
    print("Alaska 511 Road Events Fetcher")
    print("=" * 60)

    events  = fetch_511ak_events()
    cameras = fetch_511ak_cameras()

    if not events and not cameras:
        return

    filtered_events = filter_events(events) if events else []
    
    signals  = [event_to_signal(ev) for ev in filtered_events]
    signals += [camera_to_signal(cam) for cam in cameras]

    # Log coverage
    with_coords = sum(1 for s in signals if s.get("lat") and s.get("lng"))
    print(f"  Signals with coordinates: {with_coords}/{len(signals)}")

    type_counts = {"camera": len(cameras)} if cameras else {}
    for ev in filtered_events:
        t = (ev.get("type") or "unknown").lower()
        type_counts[t] = type_counts.get(t, 0) + 1
    for t, n in sorted(type_counts.items()):
        print(f"    {t}: {n}")

    if args.dry_run:
        print("\n[DRY RUN] First 3 signals:")
        for s in signals[:3]:
            print(json.dumps(s, indent=2))
        print(f"\n[DRY RUN] Would have POSTed {len(signals)} signals.")
        return

    post_signals(signals)

    # NEW: Write to data/511ak.json for standard pipeline ingestion
    for s in signals:
        if "hash" not in s:
            s["hash"] = s.get("id")
    import os
    os.makedirs("data", exist_ok=True)
    with open("data/511ak.json", "w") as f:
        json.dump(signals, f, indent=2)

    print("=" * 60)
    print(f"✓ Done. {len(signals)} 511AK road signals processed and saved to data/511ak.json.")


if __name__ == "__main__":
    main()
