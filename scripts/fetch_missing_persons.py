#!/usr/bin/env python3
"""
AlaskaIntel MMIP / Missing or Murdered Indigenous Persons Pipeline
Ingests active missing persons data from the official authoritative source:
Alaska Department of Public Safety (DPS) Missing Persons Database API CSV.
Filters strictly for `Race == 'I'` (American Indian / Alaska Native).

Outputs strict `MMIPCase` formatted JSON for the AlaskaIntel frontend.
"""

import os
import csv
import json
import requests
import io
import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
try:
    import pdfplumber
    PDF_ENABLED = True
except ImportError:
    PDF_ENABLED = False
from typing import List, Dict
from pathlib import Path
from geo_dict import geocode_text
import boto3
from botocore.config import Config
import subprocess

LOCAL_MMIP_PATH = 'data/missing-persons/cases.json'
PUBLIC_MMIP_PATH = '../www.alaskaintel.com/public/data/missing-persons/cases.json'
CACHE_PATH = 'data/missing-persons/bulletin_age_cache.json'

CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

# Load R2 credentials
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

R2_BUCKET = os.getenv("R2_BUCKET", "srv01-alaskaintel")
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "")
R2_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_ENDPOINT = os.getenv("R2_ENDPOINT", f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com" if R2_ACCOUNT_ID else "")

# DPS Official Public Missing Persons CSV
DPS_CSV_URL = "https://publicdatasets.dps.alaska.gov/api/MissingPersons/download"

def save_json(filepath: str, data: List[Dict]):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def generate_id(source: str, ref_id: str) -> str:
    """Standardize IDs across sources"""
    return f"AK-{source.upper()}-{ref_id}"

def clean_agency_location(agency: str) -> str:
    if not agency:
        return "Unknown"
    s = agency.upper()
    replacements = [
        'AST ENFORCEMENT', 'AST ENFRCMENT RURAL', 'AST INVESTIGATIONS',
        'POLICE DEPARTMENT', 'POLICE DEPT/WARRANTS', 'AIRPORT POLICE/FIRE',
        'BOROUGH', 'AWT', 'DPS', 'AST'
    ]
    for r in replacements:
        s = s.replace(r, '')
    
    if 'ANCH' in s or 'ABI MISSING PERSONS' in s:
        return 'Anchorage'
        
    cleaned = s.strip().title()
    return cleaned if cleaned else "Unknown"

def resolve_age_from_bulletin(pdf_url: str, cache_store: dict) -> int:
    """Download PDF, extract text natively, parse with Multi-Regex, return age. Uses cache to prevent duplicates."""
    if not PDF_ENABLED: return 0
    if pdf_url in cache_store: return cache_store[pdf_url]
    
    age = 0
    try:
        import urllib3
        urllib3.disable_warnings()
        r = requests.get(pdf_url, verify=False, timeout=15)
        r.raise_for_status()
        
        extracted_text = ""
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            for page in pdf.pages:
                extracted_text += page.extract_text() or ""
                
        # Primary Explicit Match
        age_match = re.search(r'(?i)(?:Age|AGE)[\s:]*([0-9]{1,3})', extracted_text)
        if age_match:
            age = int(age_match.group(1))
        else:
            # Secondary DOB Match and Calculation
            dob_match = re.search(r'(?i)(?:DOB|Date of Birth)[\s:]*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})', extracted_text)
            if dob_match:
                dob_str = dob_match.group(1).replace('-', '/')
                try:
                    dob_dt = datetime.strptime(dob_str, "%m/%d/%Y")
                except:
                    try:
                        dob_dt = datetime.strptime(dob_str, "%m/%d/%y")
                    except:
                        dob_dt = None
                
                if dob_dt:
                    today = datetime.now()
                    age = today.year - dob_dt.year - ((today.month, today.day) < (dob_dt.month, dob_dt.day))
                    
        cache_store[pdf_url] = age
        return age
    except Exception as e:
        cache_store[pdf_url] = 0
        return 0

def fetch_bulletins() -> Dict[str, Dict[str, str]]:
    """Scrape the DPS Bulletin page for PDFs and thumbnails."""
    print("Fetching Missing Persons Bulletins for photo mapping...")
    bulletin_url = "https://dps.alaska.gov/AST/ABI/MissingPerson/MPBulletin"
    bulletins = {}
    try:
        r = requests.get(bulletin_url, verify=False, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        
        for a_tag in soup.find_all('a'):
            href = a_tag.get('href', '')
            if '/getmedia/' in href:
                title = a_tag.get('title', '').strip()
                if not title:
                    title = href.split('/')[-1].replace('.pdf', '')
                
                img_tag = a_tag.find('img')
                if img_tag:
                    img_src = img_tag.get('src', '')
                    bulletins[title.lower()] = {
                        "bulletin": f"https://dps.alaska.gov{href}",
                        "image": f"https://dps.alaska.gov{img_src}"
                    }
    except Exception as e:
        print(f"Failed to fetch bulletins: {e}")
    
    print(f"  -> Extracted {len(bulletins)} bulletin media links.")
    return bulletins

def parse_dps_csv(bulletins) -> List[Dict]:
    """Fetch and parse Alaska DPS Missing Persons CSV for all races."""
    print(f"Fetching official CSV from {DPS_CSV_URL}...")
    
    # Load Age Cache
    age_cache = {}
    cache_file = Path(CACHE_PATH)
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as cf:
                age_cache = json.load(cf)
        except Exception:
            pass
            
    try:
        resp = requests.get(DPS_CSV_URL, verify=False, timeout=30)
        resp.raise_for_status()
        
        lines = resp.content.decode('utf-8').splitlines()
        reader = csv.DictReader(lines)
        
        cases = []
        found_ids = set()
        
        for r in reader:
            # Clean keys - sometimes DPS format has trailing spaces in headers
            row = {k.strip(): v.strip() if isinstance(v, str) else v for k, v in r.items() if k is not None}
            
            # Extract basic info
            last_name = row.get('Last Name', '')
            first_name = row.get('First Name', '')
            case_no = row.get('Case Number', '')
            
            if not last_name or not first_name or not case_no or case_no in found_ids:
                continue
            found_ids.add(case_no)
                
            name = f"{first_name} {last_name}".strip().title()
            sex_val = row.get('Sex', 'Unknown')
            race = row.get('Race', 'Unknown')
            
            # Determine indigenous status (Race == 'I')
            is_indigenous = (race == 'I')
            
            agency = row.get('Investigating Agency', 'Unknown Agency')
            date_str = row.get('Date Last Contacted', '')
            
            # Format Date
            last_seen = ""
            if date_str:
                try:
                    dt = datetime.strptime(date_str, "%m/%d/%Y")
                    last_seen = dt.strftime("%Y-%m-%d")
                except ValueError:
                    last_seen = date_str
            
            if not last_seen:
                last_seen = datetime.now(timezone.utc).strftime('%Y-%m-%d')
                
            coords = geocode_text(agency)
            if not coords:
                coords = [64.2008, -149.4937]
                
            # Try to match the bulletin photo using last name
            # This is heuristic since bulletin titles are like "Williams" or "SmithG"
            ln_lower = last_name.lower().replace(" ", "").replace("-", "")
            fn_lower = first_name.lower().replace(" ", "")
            
            matched_image = None
            matched_bulletin = None
            
            # Direct match check
            if ln_lower in bulletins:
                matched_image = bulletins[ln_lower]["image"]
                matched_bulletin = bulletins[ln_lower]["bulletin"]
            else:
                # Fuzzy match over bulletin keys
                for b_key, b_data in bulletins.items():
                    b_key_clean = b_key.replace(" ", "").replace("-", "")
                    # Match if last name is in the bulletin key, and maybe first initial
                    if ln_lower in b_key_clean:
                        matched_image = b_data["image"]
                        matched_bulletin = b_data["bulletin"]
                        break
            
            # Base Source link
            sources = ["https://vccb.alaska.gov/missing-persons-mmip/"]
            if matched_bulletin:
                sources.insert(0, matched_bulletin)
                
            # Optional NLP Age extraction if bulletin matched
            case_age = 0
            if matched_bulletin and PDF_ENABLED:
                case_age = resolve_age_from_bulletin(matched_bulletin, age_cache)
                
            # Build Base Case
            base_case = {
                "id": generate_id('DPS', case_no),
                "name": name,
                "age": case_age,
                "gender": "Female" if sex_val == 'F' else "Male" if sex_val == 'M' else "Unknown",
                "indigenous_status": is_indigenous,
                "tribal_affiliation": "",
                "status": "active",
                "status_history": [
                    { "status": "active", "date": last_seen }
                ],
                "last_seen_date": last_seen,
                "last_seen_location": {
                    "name": clean_agency_location(agency),
                    "lat": coords[0],
                    "lng": coords[1]
                },
                "case_type": "missing",
                "description": f"Officially reported to {clean_agency_location(agency)}. Case #{case_no}.",
                "source_links": sources,
                "agency": agency.title(),
                "contact_info": agency.title(),
                "confidence": "High",
                "image": matched_image,
                "image_source": "DPS Bulletin" if matched_image else "",
                "image_verified": bool(matched_image),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            cases.append(base_case)
            
        # Save cache back
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, 'w') as cf:
            json.dump(age_cache, cf, indent=2)
            
    except Exception as e:
        print(f"Error fetching/parsing DPS CSV: {e}")
        
    print(f"  -> Extracted {len(cases)} cases from authoritative database.")
    
    # Sort to place newest missing persons at the top
    cases.sort(key=lambda x: x.get('last_seen_date', ''), reverse=True)
    return cases

def upload_to_r2(local_path: str, r2_key: str):
    """Upload freshly generated cases.json to Cloudflare R2 automatically"""
    if not R2_KEY_ID or not R2_SECRET or not R2_ENDPOINT:
        print("  ⚠️  R2 credentials not deployed to environment — skipping bucket sync")
        return
        
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=R2_ENDPOINT,
            aws_access_key_id=R2_KEY_ID,
            aws_secret_access_key=R2_SECRET,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
        
        with open(local_path, "rb") as f:
            s3.put_object(
                Bucket=R2_BUCKET,
                Key=r2_key,
                Body=f.read(),
                ContentType="application/json",
            )
        print(f"✓ Cloudflare R2 Sync Complete: s3://{R2_BUCKET}/{r2_key}")
    except Exception as e:
        print(f"  ✗ Failed to upload to R2: {e}")

def github_push(paths: List[str]):
    """Automatically commit and push the updated json data to GitHub"""
    try:
        print("Committing to GitHub tracking...")
        for p in paths:
            subprocess.run(["git", "add", p], check=True, stdout=subprocess.DEVNULL)
            
        # Commit will fail if no changes, so we capture output
        res = subprocess.run(["git", "commit", "-m", "chore(data): auto-sync missing persons datalake updates [skip ci]"], capture_output=True)
        if res.returncode == 0:
            subprocess.run(["git", "push"], check=True, stdout=subprocess.DEVNULL)
            print("✓ GitHub Data Commit Pushed")
        else:
            print("✓ GitHub Data Sync: No new changes to commit")
    except Exception as e:
        print(f"  ✗ GitHub Sync Error: {e}")

def main():
    print("==================================================")
    print("Missing Persons Intelligence Pipeline (All Races)")
    print("==================================================")
    
    # 1) Fetch Bulletin image map
    bulletins = fetch_bulletins()
    
    # 2) Parse official API CSV drops (Master Dataset - All Races)
    cases = parse_dps_csv(bulletins)
    
    # 3) Output the results to the unified data directory
    out_path = Path("data/missing-persons/cases.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(cases, f, indent=2)
    print(f"✓ Saved backend dataset to {out_path}")
    
    # Mirror directly to frontend static directory for hot-reloading
    frontend_path = Path(PUBLIC_MMIP_PATH)
    frontend_path.parent.mkdir(parents=True, exist_ok=True)
    with open(frontend_path, "w") as f:
        json.dump(cases, f, indent=2)
    print(f"✓ Mirrored frontend payload to {frontend_path}")
    
    # 4) Automate Cloud Sync & Github Versioning
    upload_to_r2(str(out_path), "public/data/missing-persons/cases.json")
    github_push([str(out_path), str(frontend_path)])

if __name__ == '__main__':
    main()
