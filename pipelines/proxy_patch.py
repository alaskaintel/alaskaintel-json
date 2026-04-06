import os

PROXY_MAP = {
    # Name from feedCatalog.ts / fetch_intel.py -> proxy slug
    "RCA Issued Orders": "https://proxy.alaskaintel.com/rss/rca-orders",
    "DEC Air Quality Advisories": "https://proxy.alaskaintel.com/rss/dec-air",
    "Alaska Marine Highway": "https://proxy.alaskaintel.com/rss/dot-amhs",
    "AK Dept of Labor": "https://proxy.alaskaintel.com/rss/labor",
    "NOAA Fisheries Alaska": "https://proxy.alaskaintel.com/rss/noaa-fisheries",
    "USACE Alaska District": "https://proxy.alaskaintel.com/rss/usace",
    "National Fire Center": "https://proxy.alaskaintel.com/rss/nifc",
    "Alaska Legislature News": "https://proxy.alaskaintel.com/rss/legislature",
    "Alaska State Troopers": "https://proxy.alaskaintel.com/rss/ast",
    "AST Dispatch": "https://proxy.alaskaintel.com/rss/ast" # Just in case
}

URLS_TO_REPLACE = {
    # Direct mappings that we know are failing and have proxies
    "https://poa.usace.army.mil/Contact/RSS": "https://proxy.alaskaintel.com/rss/usace",
    "https://fisheries.noaa.gov/region/alaska/rss": "https://proxy.alaskaintel.com/rss/noaa-fisheries",
    "https://www.fisheries.noaa.gov/region/alaska/rss": "https://proxy.alaskaintel.com/rss/noaa-fisheries",
    "https://nifc.gov/rss": "https://proxy.alaskaintel.com/rss/nifc",
    "https://www.nifc.gov/rss": "https://proxy.alaskaintel.com/rss/nifc",
    "https://dps.alaska.gov/RSS": "https://proxy.alaskaintel.com/rss/ast",
    "https://dec.alaska.gov/Applications/Air/airtoolsweb/AqAdvisories/Index/Rss": "https://proxy.alaskaintel.com/rss/dec-air"
}

def patch_file(filepath):
    if not os.path.exists(filepath):
        print(f"Not found: {filepath}")
        return
        
    with open(filepath, 'r') as f:
        content = f.read()
        
    for old, new in URLS_TO_REPLACE.items():
        content = content.replace(f'"{old}"', f'"{new}"')
        content = content.replace(f"'{old}'", f"'{new}'")
        
    with open(filepath, 'w') as f:
        f.write(content)
    print(f"Patched {filepath}")

patch_file('fetch_intel.py')
patch_file('../../frontends/www.alaskaintel.com/src/data/feedCatalog.ts')
