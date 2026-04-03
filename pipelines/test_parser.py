import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime

url = "https://www.akconcerts.com/"
response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
soup = BeautifulSoup(response.text, 'html.parser')

events = []
current_date = None
year = datetime.now().year

# The actual dates look like "Wednesday March 25th"
# But sometimes they might have hidden spans or different tags. We just parse block text.
date_pattern = re.compile(r'^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+([A-Z][a-z]+)\s+(\d{1,2})(st|nd|rd|th)?(,*)$', re.IGNORECASE)

for element in soup.stripped_strings:
    text = str(element).strip()
    if not text: continue
    
    m = date_pattern.match(text)
    if m:
        month_str = m.group(2)
        day_str = m.group(3)
        try:
            current_date = datetime.strptime(f"{year} {month_str} {day_str}", "%Y %B %d")
            print(f"--- PARSED DATE: {current_date.strftime('%Y-%m-%d')} ---")
        except Exception as e:
            pass
        continue
        
    if current_date and ('–' in text or '-' in text) and len(text) > 10:
        print(f"EVENT: {text}")

