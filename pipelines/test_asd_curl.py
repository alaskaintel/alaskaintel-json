from curl_cffi import requests
from bs4 import BeautifulSoup

url = "https://www.asdk12.org/all-news"
try:
    headers = {'User-Agent': 'Mozilla/5.0'}
    r = requests.get(url, impersonate="chrome110", headers=headers, timeout=15)
    print("Status:", r.status_code)
    
    soup = BeautifulSoup(r.text, 'html.parser')
    links = []
    for a in soup.find_all('a'):
        text = a.text.strip()
        href = a.get('href', '')
        if len(text) > 10 and ('news' in href.lower() or 'article' in href.lower() or 'post' in href.lower()):
            links.append((text, href))
    
    print(f"Found {len(links)} potential article links:")
    for text, href in links[:15]:
        print(f" - {text} -> {href}")
        
except Exception as e:
    print("Error:", e)
