import requests
from bs4 import BeautifulSoup

url = "https://dec.alaska.gov/Applications/SPAR/PublicMVC/PERP/SpillSearch"
r = requests.get(url, verify=False)
soup = BeautifulSoup(r.text, 'html.parser')
tables = soup.find_all('table')
print(f"Found {len(tables)} tables")
if tables:
    print(tables[0].text[:500])
else:
    print("No tables found. It might be dynamically loaded via AJAX.")
