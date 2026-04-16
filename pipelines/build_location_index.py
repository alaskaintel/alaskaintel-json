import json
import os
import re

DATA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LATEST_INTEL_PATH = os.path.join(DATA_DIR, 'latest_intel.json')
PLACES_PATH = os.path.join(DATA_DIR, 'alaska-places.json')
HIGHWAYS_PATH = os.path.join(DATA_DIR, 'alaska_highways.json')

# Region Fallbacks as defined
REGION_CENTROIDS = {
    'Mat-Su': [61.58, -149.4],
    'Matanuska-Susitna': [61.58, -149.4],
    'Interior': [64.83, -147.71], # Fairbanks approx
    'Kenai Peninsula': [60.55, -151.25],
    'Kenai': [60.55, -151.25],
    'Southeast': [58.30, -134.41],
    'Southcentral': [61.21, -149.90],
    'Western': [60.79, -161.75],
    'Northern': [71.29, -156.78],
    'Statewide': [64.2008, -149.4937], # Center of AK
    'Aleutians': [53.88, -166.53],
    'Bristol Bay': [58.80, -157.00],
    'Copper River': [62.10, -145.53],
    'Prince William Sound': [60.69, -147.16]
}

def load_json(path):
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return None

def main():
    intel_data = load_json(LATEST_INTEL_PATH)
    if not intel_data:
        print("No latest_intel.json found.")
        return

    places_data = load_json(PLACES_PATH) or []
    places = {}
    for p in places_data:
        places[p['name'].lower()] = [p['lat'], p['lng']]
        for alias in p.get('aliases', []):
            places[alias.lower()] = [p['lat'], p['lng']]

    highways = load_json(HIGHWAYS_PATH) or {}
    
    # Pre-compute highway midpoints and name mapping
    highway_midpoints = {}
    highway_name_map = {}
    
    for h_key, h_data in highways.items():
        name = h_data['name'].lower()
        highway_name_map[name] = h_key
        # Extract alternative names like " Parks Highway" -> "parks"
        highway_name_map[h_key.lower()] = h_key
        
        mileposts = h_data.get('mileposts', [])
        if mileposts:
            mid_mp = mileposts[len(mileposts)//2]
            highway_midpoints[h_key] = [mid_mp['lat'], mid_mp['lng']]

    updated_count = 0
    resolved_count = 0

    for item in intel_data:
        resolved_coords = None
        
        # 1. Try: highway + milepost from address_detail
        address_detail = item.get('address_detail', '')
        if address_detail:
            # Look for patterns like "mile 39 of the Richardson Highway" or "Mile 265 Parks Highway"
            mile_match = re.search(r'mile\s+(\d+)', address_detail, re.IGNORECASE)
            if mile_match:
                mile_num = int(mile_match.group(1))
                matched_hw_key = None
                for hw_name, hw_key in highway_name_map.items():
                    if hw_name in address_detail.lower():
                        matched_hw_key = hw_key
                        break
                
                if matched_hw_key:
                    hw_data = highways.get(matched_hw_key)
                    if hw_data:
                        # Find closest milepost or exact
                        mps = hw_data.get('mileposts', [])
                        closest = min(mps, key=lambda x: abs(x['mile'] - mile_num))
                        if abs(closest['mile'] - mile_num) <= 5: # Within 5 miles is good enough
                            resolved_coords = [closest['lat'], closest['lng']]

        # 3. Try: highway name only (Midpoint)
        if not resolved_coords and address_detail:
            for hw_name, hw_key in highway_name_map.items():
                if hw_name in address_detail.lower() and hw_key in highway_midpoints:
                    resolved_coords = highway_midpoints[hw_key]
                    break
        
        # 2. Try: city name in location field
        if not resolved_coords:
            loc = item.get('location', '')
            if type(loc) == str:
                # Handle Loc / Loc or Loc, AK
                loc_parts = re.split(r'[/,]', loc)
                for part in loc_parts:
                    part_lower = part.strip().lower()
                    if part_lower in places:
                        resolved_coords = places[part_lower]
                        break

        # 4. Fallback: region centroid
        if not resolved_coords:
            # Check for region property directly
            region = item.get('region', '')
            if region and region in REGION_CENTROIDS:
                resolved_coords = REGION_CENTROIDS[region]
            else:
                # Parse dataTag for region
                data_tag = item.get('dataTag', '')
                if data_tag:
                    region_match = re.search(r'\[Region:\s*([^\]]+)\]', data_tag)
                    if region_match:
                        parsed_region = region_match.group(1).strip()
                        if parsed_region in REGION_CENTROIDS:
                            resolved_coords = REGION_CENTROIDS[parsed_region]

        if resolved_coords:
            item['coordinates'] = resolved_coords
            resolved_count += 1
        
        updated_count += 1

    with open(LATEST_INTEL_PATH, 'w') as f:
        json.dump(intel_data, f, indent=2)

    print(f"Location resolution complete. Resolved {resolved_count}/{updated_count} ({(resolved_count/updated_count)*100:.1f}%) incidents.")

if __name__ == '__main__':
    main()
