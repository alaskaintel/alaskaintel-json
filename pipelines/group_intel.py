import math
from typing import List, Dict
from datetime import datetime

def distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance between two points in miles using the Haversine formula."""
    R = 3959.0 # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def group_signals(signals: List[Dict]) -> List[Dict]:
    """
    Groups signals that are spatially (< 1.5 miles) and temporally (< 45 mins) close.
    The highest-impact signal in the cluster becomes the 'parent', and others are
    folded into its 'subSources' array to reduce map clutter.
    """
    grouped_data = []
    processed_hashes = set()
    
    # Sort signals by impact score so the highest impact signal becomes the "parent"
    sorted_signals = sorted(signals, key=lambda x: x.get('impactScore', 0), reverse=True)
    
    for item in sorted_signals:
        h = item.get('hash')
        if not h or h in processed_hashes:
            continue
            
        parent = item.copy()
        processed_hashes.add(h)
        
        # Check coordinates and timestamp
        lat1 = parent.get('lat')
        lng1 = parent.get('lng')
        ts1_str = parent.get('timestamp')
        
        if lat1 is not None and lng1 is not None and ts1_str:
            try:
                ts1 = datetime.fromisoformat(ts1_str.replace('Z', '+00:00'))
            except ValueError:
                ts1 = None
                
            if ts1:
                # Find children that match spatial-temporal limits
                children = []
                for other in sorted_signals:
                    other_h = other.get('hash')
                    if not other_h or other_h in processed_hashes:
                        continue
                        
                    lat2 = other.get('lat')
                    lng2 = other.get('lng')
                    ts2_str = other.get('timestamp')
                    
                    if lat2 is not None and lng2 is not None and ts2_str:
                        try:
                            ts2 = datetime.fromisoformat(ts2_str.replace('Z', '+00:00'))
                            time_diff_mins = abs((ts1 - ts2).total_seconds()) / 60
                            dist_miles = distance_miles(lat1, lng1, lat2, lng2)
                            
                            if dist_miles <= 1.5 and time_diff_mins <= 45:
                                # It's a match! It belongs to this incident cluster.
                                children.append(other)
                                processed_hashes.add(other_h)
                        except ValueError:
                            continue
                
                if children:
                    parent['isGrouped'] = True
                    # Initialize subSources if it doesn't exist
                    if 'subSources' not in parent:
                        parent['subSources'] = []
                    
                    # Add original parent as a subsource so we don't lose its reference
                    # Then add the children
                    mini_parent = {k: v for k, v in parent.items() if k not in ('subSources', 'isGrouped')}
                    parent['subSources'].append(mini_parent)
                    parent['subSources'].extend(children)
                    
                    # Update metadata to reflect group
                    parent['sourceAttribution'] = f"Multiple Sources ({len(children) + 1} reports)"
                    # Optionally boost the parent impact slightly due to corroboration
                    parent['impactScore'] = min(100, parent.get('impactScore', 40) + (len(children) * 5))
        
        grouped_data.append(parent)
        
    return grouped_data
