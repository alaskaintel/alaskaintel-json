import requests
import pdfplumber
import io
import re
from bs4 import BeautifulSoup

def fetch_top_bulletins(limit=10):
    print("Fetching MPBulletins...")
    bulletin_url = "https://dps.alaska.gov/AST/ABI/MissingPerson/MPBulletin"
    bulletins = []
    
    # Needs verify=False and standard headers since dps.alaska.gov blocks some bots
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
    
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    try:
        r = requests.get(bulletin_url, verify=False, timeout=30, headers=headers)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        
        for a_tag in soup.find_all('a'):
            href = a_tag.get('href', '')
            if '/getmedia/' in href:
                # Ensure there's an image thumbnail to prove it's a real bulletin link
                if a_tag.find('img'):
                    title = a_tag.get('title', '').strip() or href.split('/')[-1]
                    full_url = f"https://dps.alaska.gov{href}"
                    
                    if full_url not in [b['url'] for b in bulletins]:
                        bulletins.append({"title": title, "url": full_url})
                        if len(bulletins) >= limit:
                            break
    except Exception as e:
        print(f"Failed to fetch bulletins: {e}")
        
    return bulletins

def extract_metadata_from_pdf(pdf_bytes):
    extracted_text = ""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                extracted_text += text + "\n"
    
    # Try multiple regex patterns commonly found on police bulletins
    # Examples: "Age: 24", "AGE: 34 YOA", "DOB: 12/04/1990", "Date of Birth: 04-12-1980"
    age = None
    dob = None
    
    # Look for DOB
    dob_match = re.search(r'(?i)(?:DOB|Date of Birth)[\s:]*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})', extracted_text)
    if dob_match:
        dob = dob_match.group(1)
        # We can calculate exact age if DOB is found, but for now just capture it
        
    # Look for explicit Age
    age_match = re.search(r'(?i)(?:Age|AGE)[\s:]*([0-9]{1,3})', extracted_text)
    if age_match:
        age = age_match.group(1)
        
    # Look for "Height: 5'10" or similar as secondary test
    height_match = re.search(r'(?i)(?:Height|HGT)[\s:]*([0-9\']+\s*[0-9]+|[\d]\'[\d]{1,2})', extracted_text)
    height = height_match.group(1) if height_match else None
        
    return {
        "text": extracted_text[:100].replace('\n', ' ') + "...", # snippet
        "extracted_age": age,
        "extracted_dob": dob,
        "extracted_height": height
    }

def main():
    bulletins = fetch_top_bulletins(10)
    print(f"Found {len(bulletins)} bulletins. Analyzing...\n")
    
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    for i, b in enumerate(bulletins):
        print(f"[{i+1}/10] {b['title']}")
        print(f"  URL: {b['url']}")
        
        try:
            r = requests.get(b['url'], verify=False, timeout=15)
            r.raise_for_status()
            pdf_bytes = r.content
            
            meta = extract_metadata_from_pdf(pdf_bytes)
            print(f"  -> Age: {meta['extracted_age'] or 'Not Found'}")
            print(f"  -> DOB: {meta['extracted_dob'] or 'Not Found'}")
            print(f"  -> Height: {meta['extracted_height'] or 'Not Found'}")
            
        except Exception as e:
            print(f"  -> Error parsing PDF: {e}")
        print()

if __name__ == "__main__":
    main()
