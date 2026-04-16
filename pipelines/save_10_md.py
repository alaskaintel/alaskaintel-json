import requests
import pdfplumber
import io
import re
import os
from bs4 import BeautifulSoup

def fetch_top_bulletins(limit=10):
    print("Fetching MPBulletins...")
    bulletin_url = "https://dps.alaska.gov/AST/ABI/MissingPerson/MPBulletin"
    bulletins = []
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    import urllib3
    urllib3.disable_warnings()
    
    try:
        r = requests.get(bulletin_url, verify=False, timeout=30, headers=headers)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        
        for a_tag in soup.find_all('a'):
            href = a_tag.get('href', '')
            if '/getmedia/' in href:
                # Must have img thumbnail
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
    
    age = None
    dob = None
    
    dob_match = re.search(r'(?i)(?:DOB|Date of Birth)[\s:]*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})', extracted_text)
    if dob_match: dob = dob_match.group(1)
        
    age_match = re.search(r'(?i)(?:Age|AGE)[\s:]*([0-9]{1,3})', extracted_text)
    if age_match: age = age_match.group(1)
        
    return extracted_text.strip(), age, dob

def main():
    bulletins = fetch_top_bulletins(10)
    out_dir = "data/bulletin-extracts"
    os.makedirs(out_dir, exist_ok=True)
    
    import urllib3
    urllib3.disable_warnings()
    
    for i, b in enumerate(bulletins):
        print(f"Processing [{i+1}/10] {b['title']}...")
        try:
            r = requests.get(b['url'], verify=False, timeout=15)
            r.raise_for_status()
            
            raw_text, age, dob = extract_metadata_from_pdf(r.content)
            
            clean_title = "".join([c for c in b['title'] if c.isalnum() or c in [' ', '-']]).strip().replace(' ', '_')
            if not clean_title: clean_title = f"bulletin_{i}"
            
            md_path = os.path.join(out_dir, f"{clean_title}.md")
            
            with open(md_path, "w") as f:
                f.write(f"# DPS PDF Extraction: {b['title']}\n\n")
                f.write(f"- **Source URL:** {b['url']}\n")
                f.write(f"- **Extracted Age:** {age or 'Not Found'}\n")
                f.write(f"- **Extracted DOB:** {dob or 'Not Found'}\n\n")
                f.write(f"## Raw Text Dump\n\n```text\n{raw_text}\n```\n")
            print(f"  -> Saved {md_path}")
            
        except Exception as e:
            print(f"  -> Error: {e}")

if __name__ == "__main__":
    main()
