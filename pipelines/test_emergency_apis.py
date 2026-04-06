import requests

print("--- NWS Alaska ---")
try:
    url = "https://api.weather.gov/alerts/active.atom?area=AK"
    r = requests.get(url, headers={'User-Agent': 'AlaskaIntel (admin@alaskaintel.com)'}, timeout=10)
    print("NWS Status:", r.status_code)
    if r.status_code == 200:
        print("NWS snippet:", r.text[:200])
except Exception as e:
    print("NWS Error:", e)

print("\n--- USGS Volcano ---")
try:
    # Let's try to query the new API if possible, or just the main RSS page
    url = "https://volcanoes.usgs.gov/vhp-updates/rss"
    r = requests.get(url, headers={'User-Agent': 'AlaskaIntel'}, timeout=10)
    print("USGS Status:", r.status_code)
    if r.status_code == 200:
        print("USGS snippet:", r.text[:200])
except Exception as e:
    print("USGS Error:", e)
    
try:
    url = "https://volcanoes.usgs.gov/vhp-updates/rss?observatory=AVO"
    r = requests.get(url, headers={'User-Agent': 'AlaskaIntel'}, timeout=10)
    print("USGS AVO Status:", r.status_code)
    if r.status_code == 200:
        print("USGS AVO snippet:", r.text[:200])
except Exception as e:
    pass
