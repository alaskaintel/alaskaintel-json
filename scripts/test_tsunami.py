import requests

urls = [
    "https://tsunami.gov/events/xml/PAAQAtom.xml",
    "https://api.weather.gov/alerts/active.atom?area=AK"
]

for url in urls:
    try:
        r = requests.get(url, headers={'User-Agent': 'AlaskaIntel'}, timeout=10)
        print(f"Status for {url}: {r.status_code}")
    except Exception as e:
        print(f"Error for {url}: {e}")
