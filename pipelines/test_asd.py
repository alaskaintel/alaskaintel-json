import requests
from bs4 import BeautifulSoup

url = "https://www.asdk12.org/all-news"
try:
    headers = {'User-Agent': 'Mozilla/5.0'}
    r = requests.get(url, headers=headers, timeout=10)
    print("Status:", r.status_code)
    
    soup = BeautifulSoup(r.text, 'html.parser')
    for a in soup.find_all('a'):
        text = a.text.strip()
        if len(text) > 15 and ('News' in a.get('href', '') or 'article' in a.get('href', '')):
            print("Link:", text, "->", a.get('href'))
            
    # Or print some common div classes
    print("\nx-axis elements:")
    for d in soup.find_all('h1'):
        print("H1:", d.text)
    for d in soup.find_all('h2'):
        print("H2:", d.text)
except Exception as e:
    print("Error:", e)
