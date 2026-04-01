#!/usr/bin/env python3
"""
Alaska Aviation Fetcher
Pulls Temporary Flight Restrictions (TFRs) from the FAA and
Alaska-specific airport status/delay information.
Outputs structured JSON to data/aviation.json

Sources:
  - FAA TFR GeoJSON feed
  - FAA Airport Status API
"""

import json
import os
import re
import requests
from datetime import datetime, timezone

# FAA TFR feed (GeoJSON)
TFR_URL = "https://tfr.faa.gov/tfr2/list.json"
TFR_DETAIL_URL = "https://tfr.faa.gov/save_pages/detail_{notam_id}.html"

# FAA Airport Status (no auth required)
AIRPORT_STATUS_URL = "https://nasstatus.faa.gov/api/airport-status-information"

# Key Alaska airports
ALASKA_AIRPORTS = [
    {"code": "ANC", "name": "Ted Stevens Anchorage International", "lat": 61.174, "lng": -149.996},
    {"code": "FAI", "name": "Fairbanks International", "lat": 64.815, "lng": -147.856},
    {"code": "JNU", "name": "Juneau International", "lat": 58.355, "lng": -134.576},
    {"code": "ADQ", "name": "Kodiak Airport", "lat": 57.750, "lng": -152.494},
    {"code": "BET", "name": "Bethel Airport", "lat": 60.780, "lng": -161.838},
    {"code": "OME", "name": "Nome Airport", "lat": 64.512, "lng": -165.445},
    {"code": "SIT", "name": "Sitka Rocky Gutierrez", "lat": 57.047, "lng": -135.362},
    {"code": "KTN", "name": "Ketchikan International", "lat": 55.356, "lng": -131.714},
    {"code": "BRW", "name": "Wiley Post–Will Rogers (Utqiagvik)", "lat": 71.286, "lng": -156.766},
    {"code": "ADK", "name": "Adak Airport", "lat": 51.878, "lng": -176.646},
    {"code": "CDV", "name": "Merle K. (Mudhole) Smith (Cordova)", "lat": 60.492, "lng": -145.478},
    {"code": "YAK", "name": "Yakutat Airport", "lat": 59.503, "lng": -139.660},
    {"code": "DLG", "name": "Dillingham Airport", "lat": 59.045, "lng": -158.505},
    {"code": "VDZ", "name": "Valdez Pioneer Field", "lat": 61.134, "lng": -146.248},
]

OUTPUT_PATH = os.path.join("data", "aviation.json")


def fetch_tfrs():
    """Fetch active TFRs, filtering for Alaska region."""
    print("Fetching FAA Temporary Flight Restrictions...")

    tfrs = []
    try:
        resp = requests.get(TFR_URL, timeout=30)
        resp.raise_for_status()

        # FAA TFR list.json is a simple array of TFR objects
        data = resp.json()
        if not isinstance(data, list):
            data = data.get("features", []) if isinstance(data, dict) else []

        for item in data:
            # Different formats depending on endpoint version
            props = item if not item.get("properties") else item.get("properties", {})

            state = props.get("state", "")
            # Filter for Alaska
            if state.upper() not in ("AK", "ALASKA", ""):
                continue

            # For items without state, check lat/lng bounds
            lat = props.get("lat") or props.get("latitude")
            lng = props.get("lng") or props.get("longitude")
            if lat and lng:
                try:
                    lat_f = float(lat)
                    lng_f = float(lng)
                    if not (50 <= lat_f <= 72 and -180 <= lng_f <= -129):
                        continue
                except (ValueError, TypeError):
                    if state.upper() not in ("AK", "ALASKA"):
                        continue

            tfrs.append({
                "notam_id": props.get("notam", props.get("notamNumber", "")),
                "type": props.get("type", "TFR"),
                "description": props.get("description", props.get("reason", "")),
                "effective": props.get("effectiveDate", props.get("startDate", "")),
                "expires": props.get("expireDate", props.get("endDate", "")),
                "altitude_low": props.get("altitudeLow", ""),
                "altitude_high": props.get("altitudeHigh", ""),
                "lat": lat,
                "lng": lng,
                "state": "AK",
            })

        print(f"  Found {len(tfrs)} Alaska TFRs")

    except Exception as e:
        print(f"  ⚠️  TFR fetch error: {e}")
        print("  Continuing without TFR data...")

    return tfrs


def fetch_airport_status():
    """Fetch delay/status information for Alaska airports."""
    print("Fetching Alaska airport status...")

    statuses = []
    for airport in ALASKA_AIRPORTS:
        try:
            url = f"https://nasstatus.faa.gov/api/airport-status-information?airport={airport['code']}"
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                # Airport may not be in the FAA status system; record as normal
                statuses.append({
                    "code": airport["code"],
                    "name": airport["name"],
                    "lat": airport["lat"],
                    "lng": airport["lng"],
                    "status": "normal",
                    "delays": [],
                })
                continue

            data = resp.json()
            delays = []
            if isinstance(data, dict):
                for delay in data.get("delays", []):
                    delays.append({
                        "type": delay.get("type", ""),
                        "reason": delay.get("reason", ""),
                        "avg_delay": delay.get("avgDelay", ""),
                    })

            status = "delayed" if delays else "normal"

            statuses.append({
                "code": airport["code"],
                "name": airport["name"],
                "lat": airport["lat"],
                "lng": airport["lng"],
                "status": status,
                "delays": delays,
            })
            print(f"  ✓ {airport['code']}: {status}")

        except Exception as e:
            statuses.append({
                "code": airport["code"],
                "name": airport["name"],
                "lat": airport["lat"],
                "lng": airport["lng"],
                "status": "unknown",
                "delays": [],
            })
            print(f"  ⚠️  {airport['code']}: {e}")

    return statuses


def save_data(tfrs, airports):
    """Save aviation data to JSON."""
    os.makedirs("data", exist_ok=True)

    delayed_count = sum(1 for a in airports if a["status"] == "delayed")

    output = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "source": "Federal Aviation Administration",
        "source_url": "https://www.faa.gov/",
        "tfrs": {
            "count": len(tfrs),
            "items": tfrs,
        },
        "airports": {
            "count": len(airports),
            "delayed": delayed_count,
            "stations": airports,
        },
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Saved aviation data to {OUTPUT_PATH}")
    print(f"  {len(tfrs)} TFRs, {len(airports)} airports ({delayed_count} delayed)")


def main():
    print("=" * 50)
    print("Alaska Aviation Fetcher")
    print("=" * 50)

    tfrs = fetch_tfrs()
    airports = fetch_airport_status()
    save_data(tfrs, airports)


if __name__ == "__main__":
    main()
