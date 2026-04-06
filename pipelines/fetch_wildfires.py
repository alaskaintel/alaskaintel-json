#!/usr/bin/env python3
"""
Alaska Wildfire Fetcher
Pulls active wildfire data from NIFC (National Interagency Fire Center)
and Alaska Interagency Coordination Center (AICC).
Outputs structured JSON to data/wildfires.json

Sources:
  - NIFC ArcGIS REST: active fire perimeters and incidents
  - InciWeb via NIFC feed
"""

import json
import os
import requests
from datetime import datetime, timezone

# NIFC ArcGIS feature services for active incidents
NIFC_INCIDENTS_URL = (
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
    "Active_Fires/FeatureServer/0/query"
)

# NIFC perimeters
NIFC_PERIMETERS_URL = (
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
    "Active_Fires/FeatureServer/1/query"
)

# Alaska bounding box
ALASKA_BBOX = "-180,50,-129,72"

OUTPUT_PATH = os.path.join("data", "wildfires.json")


def fetch_active_fires():
    """Fetch active fire incidents in Alaska from NIFC ArcGIS."""
    print("Fetching active wildfire incidents from NIFC...")

    params = {
        "where": "POOState = 'US-AK' OR POOState = 'AK'",
        "outFields": "*",
        "f": "json",
        "resultRecordCount": 500,
        "orderByFields": "FireDiscoveryDateTime DESC",
    }

    fires = []
    try:
        resp = requests.get(NIFC_INCIDENTS_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for feature in data.get("features", []):
            attrs = feature.get("attributes", {})
            geom = feature.get("geometry", {})

            # Parse timestamps (NIFC uses epoch milliseconds)
            discovery_ts = attrs.get("FireDiscoveryDateTime")
            discovery_iso = None
            if discovery_ts:
                discovery_iso = datetime.fromtimestamp(
                    discovery_ts / 1000, tz=timezone.utc
                ).isoformat()

            updated_ts = attrs.get("ModifiedOnDateTime") or attrs.get("CreateDateTime")
            updated_iso = None
            if updated_ts:
                updated_iso = datetime.fromtimestamp(
                    updated_ts / 1000, tz=timezone.utc
                ).isoformat()

            acres = attrs.get("DailyAcres") or attrs.get("CalculatedAcres") or 0

            fires.append({
                "id": attrs.get("IrwinID", attrs.get("OBJECTID", "")),
                "name": attrs.get("IncidentName", "Unknown Fire"),
                "status": attrs.get("IncidentTypeCategory", "Unknown"),
                "cause": attrs.get("FireCause", ""),
                "acres": acres,
                "containment_pct": attrs.get("PercentContained"),
                "discovered": discovery_iso,
                "updated": updated_iso,
                "county": attrs.get("POOCounty", ""),
                "state": "Alaska",
                "lat": geom.get("y") if geom else None,
                "lng": geom.get("x") if geom else None,
                "incident_url": f"https://inciweb.wildfire.gov/incident-information/{attrs.get('IrwinID', '')}"
                if attrs.get("IrwinID")
                else None,
            })

        print(f"  Found {len(fires)} active fire incidents")

    except requests.exceptions.HTTPError as e:
        print(f"  ⚠️  NIFC API error: {e}")
        # Fallback: try alternate query without state filter
        try:
            alt_params = {
                "where": "1=1",
                "geometry": ALASKA_BBOX,
                "geometryType": "esriGeometryEnvelope",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "*",
                "f": "json",
                "resultRecordCount": 200,
            }
            resp = requests.get(NIFC_INCIDENTS_URL, params=alt_params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            for feature in data.get("features", []):
                attrs = feature.get("attributes", {})
                geom = feature.get("geometry", {})
                fires.append({
                    "id": str(attrs.get("OBJECTID", "")),
                    "name": attrs.get("IncidentName", "Unknown Fire"),
                    "status": attrs.get("IncidentTypeCategory", "Unknown"),
                    "acres": attrs.get("DailyAcres") or 0,
                    "lat": geom.get("y") if geom else None,
                    "lng": geom.get("x") if geom else None,
                })
            print(f"  Fallback found {len(fires)} fires via spatial query")
        except Exception as ex:
            print(f"  ✗ Fallback also failed: {ex}")

    except Exception as e:
        print(f"  ✗ Error: {e}")

    return fires


def save_data(fires):
    """Save wildfire data to JSON."""
    os.makedirs("data", exist_ok=True)

    # Summary stats
    total_acres = sum(f.get("acres", 0) or 0 for f in fires)
    contained = [f for f in fires if (f.get("containment_pct") or 0) >= 100]

    output = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "source": "National Interagency Fire Center (NIFC)",
        "source_url": "https://www.nifc.gov/",
        "summary": {
            "active_fires": len(fires),
            "total_acres": total_acres,
            "fully_contained": len(contained),
        },
        "fires": fires,
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Saved {len(fires)} wildfires to {OUTPUT_PATH}")
    print(f"  Total acreage: {total_acres:,.0f}")


def main():
    print("=" * 50)
    print("Alaska Wildfire Fetcher")
    print("=" * 50)

    fires = fetch_active_fires()
    save_data(fires)


if __name__ == "__main__":
    main()
