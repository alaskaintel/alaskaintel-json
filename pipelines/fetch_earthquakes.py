#!/usr/bin/env python3
"""
Alaska Earthquake Fetcher
Pulls real-time earthquake data from the USGS Earthquake Hazards API.
Outputs structured JSON to data/earthquakes.json

API docs: https://earthquake.usgs.gov/fdsnws/event/1/
"""

import json
import os
import requests
from datetime import datetime, timezone, timedelta

USGS_API = "https://earthquake.usgs.gov/fdsnws/event/1/query"

# Alaska bounding box (generous to catch Aleutian chain)
PARAMS = {
    "format": "geojson",
    "starttime": "",  # Set dynamically
    "endtime": "",
    "minlatitude": 50.0,
    "maxlatitude": 72.0,
    "minlongitude": -180.0,
    "maxlongitude": -129.0,
    "minmagnitude": 1.5,
    "orderby": "time",
    "limit": 200,
}

OUTPUT_PATH = os.path.join("data", "earthquakes.json")


def fetch_earthquakes():
    """Fetch last 24 hours of Alaska earthquakes from USGS."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)

    params = {**PARAMS}
    params["starttime"] = start.strftime("%Y-%m-%dT%H:%M:%S")
    params["endtime"] = now.strftime("%Y-%m-%dT%H:%M:%S")

    print(f"Fetching earthquakes from USGS API...")
    print(f"  Time window: {params['starttime']} → {params['endtime']}")

    resp = requests.get(USGS_API, params=params, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    features = data.get("features", [])

    earthquakes = []
    for feature in features:
        props = feature.get("properties", {})
        geom = feature.get("geometry", {})
        coords = geom.get("coordinates", [0, 0, 0])

        earthquakes.append({
            "id": feature.get("id", ""),
            "magnitude": props.get("mag"),
            "place": props.get("place", ""),
            "time": datetime.fromtimestamp(
                props.get("time", 0) / 1000, tz=timezone.utc
            ).isoformat(),
            "updated": datetime.fromtimestamp(
                props.get("updated", 0) / 1000, tz=timezone.utc
            ).isoformat(),
            "url": props.get("url", ""),
            "detail_url": props.get("detail", ""),
            "status": props.get("status", ""),
            "tsunami": props.get("tsunami", 0),
            "type": props.get("type", "earthquake"),
            "title": props.get("title", ""),
            "alert": props.get("alert"),  # green/yellow/orange/red or null
            "felt": props.get("felt"),  # number of felt reports
            "cdi": props.get("cdi"),  # community intensity
            "mmi": props.get("mmi"),  # modified Mercalli intensity
            "sig": props.get("sig"),  # significance 0-1000
            "lat": coords[1] if len(coords) > 1 else None,
            "lng": coords[0] if len(coords) > 0 else None,
            "depth_km": coords[2] if len(coords) > 2 else None,
        })

    print(f"  Found {len(earthquakes)} earthquakes (M{PARAMS['minmagnitude']}+)")

    return earthquakes


def save_data(earthquakes):
    """Save earthquake data to JSON."""
    os.makedirs("data", exist_ok=True)

    output = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "source": "USGS Earthquake Hazards Program",
        "source_url": "https://earthquake.usgs.gov/",
        "query": {
            "region": "Alaska",
            "min_magnitude": PARAMS["minmagnitude"],
            "time_window_hours": 24,
        },
        "count": len(earthquakes),
        "earthquakes": earthquakes,
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"✓ Saved {len(earthquakes)} earthquakes to {OUTPUT_PATH}")


def main():
    print("=" * 50)
    print("Alaska Earthquake Fetcher")
    print("=" * 50)

    earthquakes = fetch_earthquakes()
    save_data(earthquakes)

    # Print quick summary
    if earthquakes:
        magnitudes = [q["magnitude"] for q in earthquakes if q["magnitude"]]
        if magnitudes:
            print(f"\n  Largest: M{max(magnitudes)}")
            print(f"  Smallest: M{min(magnitudes)}")
            print(f"  Tsunami flags: {sum(1 for q in earthquakes if q['tsunami'])}")


if __name__ == "__main__":
    main()
