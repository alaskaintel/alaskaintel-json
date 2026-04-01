import requests
from bs4 import BeautifulSoup
import datetime
import urllib3

urllib3.disable_warnings()

url = "https://dec.alaska.gov/Applications/SPAR/PublicMVC/PERP/SpillSearch"
session = requests.Session()
r = session.get(url, verify=False)
soup = BeautifulSoup(r.text, 'html.parser')

token = soup.find('input', {'name': '__RequestVerificationToken'})
token_val = token['value'] if token else ''

end_date = datetime.datetime.now()
start_date = end_date - datetime.timedelta(days=7)

payload = {
    '__RequestVerificationToken': token_val,
    'Spill_DateFrom': start_date.strftime('%m/%d/%Y'),
    'Spill_DateTo': end_date.strftime('%m/%d/%Y'),
    'Spill_SearchButton': 'Search'
}

r2 = session.post(url, data=payload, verify=False)
soup2 = BeautifulSoup(r2.text, 'html.parser')
tables2 = soup2.find_all('table')
print(f"Post responded with {len(tables2)} tables")
for t in tables2:
    rows = t.find_all('tr')
    if len(rows) > 3:
        print("Found data table with", len(rows), "rows")
        for i, row in enumerate(rows[:5]):
            cols = row.find_all(['th', 'td'])
            print(i, "|".join([c.text.strip() for c in cols]))
