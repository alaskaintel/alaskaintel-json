import os
import json
import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Path to the geojson relative to this script
GEOJSON_PATH = os.path.join(
    os.path.dirname(__file__),
    '../../public/dot-data-sets/dot-milepost/Mileposts_AKDOT_1678690473737224560.geojson'
)

# In-memory dictionary to store route -> milepost -> coordinates
# Structure: { "george parks highway": { 104: (lat, lng), ... }, ... }
MILEPOST_DATA = {}

# Highway name aliases to map common AST names to DOT GeoJSON names
HWY_ALIASES = {
    "parks highway": "george parks highway",
    "parks hwy": "george parks highway",
    "stewart highway": "stese highway", # typo catch
    "rich": "richardson highway",
    "glenn": "glenn highway",
    "seward": "seward highway",
    "dalton": "dalton highway",
    "denali": "denali highway",
    "elliott": "elliott highway",
    "haines": "haines highway",
    "sterling": "sterling highway",
    "tok": "tok cutoff highway",
    "tok cutoff": "tok cutoff highway",
    "alaska": "alaska highway",
    "taylor": "taylor highway",
    "steese": "steese highway",
    "kodiak": "kodiak",
    "petersville": "petersville road",
}

def load_milepost_data():
    """Loads the DOT GeoJSON into memory for fast lookup."""
    global MILEPOST_DATA
    if MILEPOST_DATA:
        return # Already loaded

    if not os.path.exists(GEOJSON_PATH):
        logger.warning(f"Milepost GeoJSON not found at {GEOJSON_PATH}")
        return

    try:
        with open(GEOJSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for feature in data.get('features', []):
            props = feature.get('properties', {})
            geom = feature.get('geometry', {})
            
            if not geom or geom.get('type') != 'Point':
                continue
                
            coords = geom.get('coordinates')
            if not coords or len(coords) < 2:
                continue

            # GeoJSON coordinates are [lng, lat]
            lng, lat = coords[0], coords[1]
            
            milepost = props.get('Milepost_Number')
            if milepost is None:
                continue
            
            route_name = props.get('Route_Name', '').lower()
            if not route_name:
                continue

            # Ensure route dictionary exists
            if route_name not in MILEPOST_DATA:
                MILEPOST_DATA[route_name] = {}
            
            # Save the coordinates
            MILEPOST_DATA[route_name][int(milepost)] = (lat, lng)
            
    except Exception as e:
        logger.error(f"Error loading milepost GeoJSON: {e}")


def _normalize_hwy_name(hwy_name: str) -> str:
    """Normalizes the highway name from AST reports to match DOT names."""
    hwy_lower = hwy_name.lower().strip()
    
    # Check exact aliases first
    if hwy_lower in HWY_ALIASES:
        return HWY_ALIASES[hwy_lower]
        
    # Check if a known alias is a substring
    for alias, canon in HWY_ALIASES.items():
        if alias in hwy_lower:
            return canon
            
    # Default return clean string
    return hwy_lower.replace(' hwy', ' highway')


def geocode_milemarker(highway_name: str, mile_number: float) -> Optional[Tuple[float, float]]:
    """
    Looks up a highway and mile marker in the DOT dataset and returns (lat, lng).
    Will snap to the nearest integer milepost if an exact float isn't available.
    """
    load_milepost_data()
    
    if not MILEPOST_DATA:
        return None
        
    canon_hwy = _normalize_hwy_name(highway_name)
    mile_int = int(round(float(mile_number)))

    # Direct match on normalized highway name
    hwy_data = MILEPOST_DATA.get(canon_hwy)
    
    # If no direct match, try a fuzzy match against loaded routes
    if not hwy_data:
        for loaded_hwy in MILEPOST_DATA.keys():
            if canon_hwy in loaded_hwy or loaded_hwy in canon_hwy:
                hwy_data = MILEPOST_DATA[loaded_hwy]
                break

    if not hwy_data:
        return None

    # Find the nearest integer milepost (exact match or closest neighbor)
    if mile_int in hwy_data:
        return hwy_data[mile_int]
        
    # Snap to nearest within 2 miles
    available_miles = list(hwy_data.keys())
    closest_mile = min(available_miles, key=lambda m: abs(m - mile_int))
    
    if abs(closest_mile - mile_int) <= 2:
        return hwy_data[closest_mile]

    return None

# Simple test if run directly
if __name__ == '__main__':
    print("Testing geocode_milemarker...")
    print("Parks Hwy 104:", geocode_milemarker("Parks Hwy", 104.5))
    print("Seward Highway 50:", geocode_milemarker("Seward Highway", 50))
    print("Denali Highway 103:", geocode_milemarker("Denali Highway", 103))
