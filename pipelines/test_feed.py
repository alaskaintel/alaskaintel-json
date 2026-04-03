import feedparser
import sys
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

url = sys.argv[1]
p = feedparser.parse(url)
print(f"Status: {p.get('status', 'No status')}")
if p.bozo:
    print(f"Bozo Exception: {p.bozo_exception}")
print(f"Entries: {len(p.entries)}")
