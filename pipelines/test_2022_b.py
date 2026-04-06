import sys
sys.path.append("/Users/kb/Library/Mobile Documents/com~apple~CloudDocs/ANTIGRAVITY_BUILDS/ALASKAINTEL_AG-v101/alaskaintel-data/scripts")
from backfill_ast_archive import parse_archive_snapshot

original_url = "https://dailydispatch.dps.alaska.gov/Home/Display?dateReceived=3/18/2022%2012:00:00%20AM"
timestamp = "20220615072321"

res = parse_archive_snapshot(timestamp, original_url, set())
print(f"Extracted {len(res)} items")
