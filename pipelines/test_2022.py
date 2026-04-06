import sys
sys.path.append("/Users/kb/Library/Mobile Documents/com~apple~CloudDocs/ANTIGRAVITY_BUILDS/ALASKAINTEL_AG-v101/alaskaintel-data/scripts")
from backfill_ast_archive import parse_archive_snapshot

timestamp = "20220601000000" # approximate, the parser will fetch the closest
original_url = "http://dailydispatch.dps.alaska.gov/Home/Display"

res = parse_archive_snapshot("20220615011651", original_url, set())
print(f"Extracted {len(res)} items")
if len(res) == 0:
    import requests
    from bs4 import BeautifulSoup
    import re
    resp = requests.get(f"http://web.archive.org/web/20220615011651id_/{original_url}")
    soup = BeautifulSoup(resp.text, 'html.parser')
    links = soup.find_all('a')
    print("Sample links found on page:")
    for l in links[:20]:
        print(l.get('href'))
