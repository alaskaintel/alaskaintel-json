import json
import os
import concurrent.futures
from bs4 import BeautifulSoup
from curl_cffi import requests
from urllib.parse import urljoin, urlparse

DISTRICTS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "ak_school_districts.json")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "ak_schools.json")

def find_schools(district):
    d_url = district.get("url")
    if not d_url:
        return []
    
    schools = []
    try:
        print(f"Spidering {d_url}...")
        r = requests.get(d_url, impersonate="chrome110", timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        d_domain = urlparse(d_url).netloc
        base_domain = ".".join(d_domain.split('.')[-2:]) if d_domain.count('.') >= 2 else d_domain
        
        # Thrillshare often has a .schools-menu or #schools-nav
        # Or look for dropdown menus containing "Schools"
        links = soup.find_all('a', href=True)
        
        seen_urls = set()
        for a in links:
            href = a['href']
            text = a.text.strip().lower()
            
            # Resolve relative URLs
            if href.startswith('/'):
                href = urljoin(d_url, href)
                
            parsed_href = urlparse(href)
            
            # To avoid saving every single internal page on the district, 
            # we look for characteristic signs of a school subdomain or subfolder.
            is_school = False
            
            # Condition 1: Subdomain of the district (e.g., mhs.matsuk12.us)
            if base_domain in parsed_href.netloc and parsed_href.netloc != d_domain and parsed_href.netloc.count('.') >= 2:
                if parsed_href.netloc != "www." + d_domain:
                    is_school = True
                    
            # Condition 2: Explicit Text Match (School, Elementary, High, Middle, Academy)
            elif "school" in text or "elementary" in text or "high" in text or "middle" in text or "academy" in text:
                if len(text) > 5 and len(text) < 50:
                    is_school = True
                    
            # Condition 3: Common Thrillshare URL structure (e.g., /o/mhs)
            elif href.startswith(d_url + "/o/") and len(href.split('/')) == 5:
                is_school = True
                
            if is_school:
                clean_url = f"{parsed_href.scheme}://{parsed_href.netloc}{parsed_href.path}"
                if clean_url not in seen_urls and clean_url != d_url and not clean_url.endswith('.pdf'):
                    seen_urls.add(clean_url)
                    schools.append({
                        "name": text.title() if text else "Unknown School",
                        "url": clean_url,
                        "district_id": district["id"],
                        "district_name": district["name"]
                    })
                    
    except Exception as e:
        print(f"Error spidering {d_url}: {e}")
        
    return schools

def main():
    try:
        with open(DISTRICTS_FILE, 'r') as f:
            districts = json.load(f)
    except Exception as e:
        print(f"Failed to load districts: {e}")
        return
        
    all_schools = []
    
    # We will run this concurrently to speed up the spidering
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_district = {executor.submit(find_schools, d): d for d in districts if "url" in d}
        
        for future in concurrent.futures.as_completed(future_to_district):
            school_list = future.result()
            all_schools.extend(school_list)
            
    # Always include the primary district hubs themselves as part of the total scrape list!
    for d in districts:
        if "url" in d:
            all_schools.append({
                "name": d["name"] + " (District Base)",
                "url": d["url"],
                "district_id": d["id"],
                "district_name": d["name"]
            })
            
    # Deduplicate completely identical URLs
    unique_schools = { s['url']: s for s in all_schools }.values()
    final_list = list(unique_schools)
    
    print(f"\nDiscovered {len(final_list)} total distinct K-12 endpoints (Districts + Individual Schools).")
    
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(final_list, f, indent=2)
        
    print(f"Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
