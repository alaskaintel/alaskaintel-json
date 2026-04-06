#!/usr/bin/env python3
import json
import os
import urllib.parse
from urllib.request import Request, urlopen
from bs4 import BeautifulSoup
import string

URL = "https://akconcerts.com/venues"
OUTPUT_FILE = "data/venues.json"

def get_favicon_url(domain):
    """Get a high-quality favicon URL for a given domain."""
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=128"

def main():
    print(f"Scraping venues from {URL}...")
    req = Request(URL, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        html = urlopen(req).read().decode('utf-8')
    except Exception as e:
        print(f"Error fetching {URL}: {e}")
        return

    soup = BeautifulSoup(html, 'html.parser')
    
    venues = []
    
    # Weebly structure typically uses wsite-content elements or just paragraphs.
    # Let's find all the text and links. A robust way is to just iterate over tags.
    # The markdown parser saw text elements. We can look at all the <a> tags, 
    # and find their preceding text node or heading.
    
    # Let's extract all text and links in order by walking the DOM.
    current_city = "Unknown"
    
    content_area = soup.find('div', id='wsite-content')
    if not content_area:
        content_area = soup.find('body')
        
    for p in content_area.find_all(['p', 'div', 'h2', 'h3']):
        text = p.get_text(strip=True)
        # Check if this paragraph contains just a city name, no links
        if text and not p.find('a') and text[0].isupper() and len(text.split()) <= 3:
            # Maybe it's a city name.
            # Filter out some known non-city text
            if "concert" not in text.lower() and "venue" not in text.lower() and "sign up" not in text.lower():
                current_city = text.strip(string.punctuation)
                
        # Now find anchors in this element
        for a in p.find_all('a'):
            href = a.get('href')
            name = a.get_text(strip=True)
            if href and name and name.lower() not in ['ak concerts', 'playing soon', 'bands', 'email newsletter', 'venues', 'learn', 'support ak concerts', 'more']:
                # Basic validation
                if href.startswith('http'):
                    domain = urllib.parse.urlparse(href).netloc
                    venues.append({
                        "name": name,
                        "city": current_city,
                        "website_url": href,
                        "favicon_url": get_favicon_url(domain)
                    })

    # Dedup
    seen = set()
    unique_venues = []
    for v in venues:
        key = (v['name'], v['city'])
        if key not in seen:
            seen.add(key)
            unique_venues.append(v)
            
    print(f"Found {len(unique_venues)} venues.")
    if unique_venues:
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        with open(OUTPUT_FILE, 'w') as f:
            json.dump({"venues": unique_venues}, f, indent=2)
        print(f"Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
