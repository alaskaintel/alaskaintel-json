#!/usr/bin/env python3
"""
Alaska Weather Fetcher
Pulls active weather alerts and zone forecasts from the NWS API.
Outputs structured JSON to data/weather.json

API docs: https://www.weather.gov/documentation/services-web-api
"""

import json
import os
import requests
from datetime import datetime, timezone

NWS_API = "https://api.weather.gov"
HEADERS = {
    "User-Agent": "(alaskaintel.com, contact@alaskaintel.com)",
    "Accept": "application/geo+json",
}

# Alaska NWS offices
ALASKA_OFFICES = ["AFC", "AFG", "AJK"]  # Anchorage, Fairbanks, Juneau

# Alaska state code for alerts
ALERT_PARAMS = {
    "area": "AK",
    "status": "actual",
    "message_type": "alert,update",
}

OUTPUT_PATH = os.path.join("data", "weather.json")


def fetch_alerts():
    """Fetch active NWS alerts for Alaska."""
    print("Fetching NWS active alerts for Alaska...")
    url = f"{NWS_API}/alerts/active"

    resp = requests.get(url, headers=HEADERS, params=ALERT_PARAMS, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    features = data.get("features", [])

    alerts = []
    for feature in features:
        props = feature.get("properties", {})
        geom = feature.get("geometry")

        # Extract centroid for map placement
        lat, lng = None, None
        if geom and geom.get("type") == "Polygon":
            coords = geom["coordinates"][0]
            lat = sum(c[1] for c in coords) / len(coords)
            lng = sum(c[0] for c in coords) / len(coords)
        elif geom and geom.get("type") == "Point":
            lat = geom["coordinates"][1]
            lng = geom["coordinates"][0]

        alerts.append({
            "id": props.get("id", ""),
            "event": props.get("event", ""),
            "headline": props.get("headline", ""),
            "description": (props.get("description", "") or "")[:500],
            "severity": props.get("severity", ""),
            "certainty": props.get("certainty", ""),
            "urgency": props.get("urgency", ""),
            "sender": props.get("senderName", ""),
            "effective": props.get("effective", ""),
            "expires": props.get("expires", ""),
            "areas": props.get("areaDesc", ""),
            "category": props.get("category", ""),
            "response": props.get("response", ""),
            "instruction": (props.get("instruction", "") or "")[:300],
            "lat": lat,
            "lng": lng,
        })

    print(f"  Found {len(alerts)} active alerts")
    return alerts


def fetch_observations():
    """Fetch latest observations from key Alaska stations."""
    stations = [
        ("PANC", "Anchorage"),
        ("PAFA", "Fairbanks"),
        ("PAJN", "Juneau"),
        ("PADQ", "Kodiak"),
        ("PAOM", "Nome"),
        ("PABE", "Bethel"),
        ("PABR", "Utqiagvik"),
        ("PAKN", "King Salmon"),
        ("PADK", "Adak"),
        ("PAVD", "Valdez"),
    ]

    observations = []
    for station_id, name in stations:
        try:
            url = f"{NWS_API}/stations/{station_id}/observations/latest"
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                print(f"  ⚠️  {name} ({station_id}): HTTP {resp.status_code}")
                continue

            data = resp.json()
            props = data.get("properties", {})
            geom = data.get("geometry", {})
            coords = geom.get("coordinates", [None, None])

            temp_c = props.get("temperature", {}).get("value")
            temp_f = round(temp_c * 9 / 5 + 32, 1) if temp_c is not None else None

            wind_ms = props.get("windSpeed", {}).get("value")
            wind_mph = round(wind_ms * 2.237, 1) if wind_ms is not None else None

            observations.append({
                "station": station_id,
                "name": name,
                "timestamp": props.get("timestamp", ""),
                "description": props.get("textDescription", ""),
                "temp_f": temp_f,
                "temp_c": round(temp_c, 1) if temp_c is not None else None,
                "wind_mph": wind_mph,
                "wind_direction": props.get("windDirection", {}).get("value"),
                "humidity": props.get("relativeHumidity", {}).get("value"),
                "visibility_mi": None,
                "lat": coords[1] if coords[1] is not None else None,
                "lng": coords[0] if coords[0] is not None else None,
            })
            print(f"  ✓ {name}: {props.get('textDescription', 'N/A')}")

        except Exception as e:
            print(f"  ✗ {name} ({station_id}): {e}")

    return observations


def save_data(alerts, observations):
    """Save weather data to JSON."""
    os.makedirs("data", exist_ok=True)

    output = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "source": "National Weather Service",
        "source_url": "https://weather.gov",
        "alerts": {
            "count": len(alerts),
            "items": alerts,
        },
        "observations": {
            "count": len(observations),
            "stations": observations,
        },
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Saved weather data to {OUTPUT_PATH}")
    print(f"  {len(alerts)} alerts, {len(observations)} observations")


def main():
    print("=" * 50)
    print("Alaska Weather Fetcher")
    print("=" * 50)

    alerts = fetch_alerts()
    observations = fetch_observations()
    save_data(alerts, observations)

    # Quick summary
    if alerts:
        severities = {}
        for a in alerts:
            sev = a["severity"]
            severities[sev] = severities.get(sev, 0) + 1
        print(f"\n  Alert breakdown: {severities}")


if __name__ == "__main__":
    main()
