#!/usr/bin/env python3
"""
Alaska State Trooper (AST) Daily Dispatch Scraper — ENHANCED ENTITY EXTRACTION
Scrapes the live Alaska DPS Daily Dispatch page for today's incident reports.
Extracts structured entities: suspects, charges, facility, bail, outcome, BAC, etc.
Saves to data/ast_logs.json + mirrors to public/data/ast_logs.json.

Source: https://dailydispatch.dps.alaska.gov/
"""

import json
import os
import re
import shutil
import hashlib
import requests
from datetime import datetime, timezone, timedelta
from geo_dict import geocode_text
from geo_milepost import geocode_milemarker

try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
except Exception as e:
    print(f"Warning: spaCy not loaded for NER ({e})")
    nlp = None

FILE_PATH = 'data/ast_logs.json'
PUBLIC_PATH = '../www.alaskaintel.com/public/data/ast_logs.json'
BASE_URL = 'https://dailydispatch.dps.alaska.gov'
DISPATCH_URL = BASE_URL + '/Home/Display'

# Alaska correctional facilities short-code to full name
FACILITY_MAP = {
    'FCC':          'Fairbanks Correctional Center',
    'MSPT':         'Mat-Su Pretrial Facility',
    'WCC':          'Wildwood Correctional Center',
    'Wildwood':     'Wildwood Correctional Complex',
    'Hiland':       'Hiland Mountain Correctional Center',
    'LCCC':         'Lemon Creek Correctional Center',
    'LMCC':         'Lemon Creek Correctional Center',
    'ANVSA':        'Anvil Mountain Correctional Center',
    'Anvil':        'Anvil Mountain Correctional Center',
    'KPU':          'Ketchikan Pretrial Unit',
    'GCCC':         'Goose Creek Correctional Center',
    'Goose Creek':  'Goose Creek Correctional Center',
    'YYF':          'Yukon-Kuskokwim Correctional Center',
    'YKCC':         'Yukon-Kuskokwim Correctional Center',
    'JBER':         'JBER Correctional Facility',
    'AYA':          'Alaska Youth Authority',
}

REGION_MAP = {
    'soldotna': 'Southcentral', 'kenai': 'Southcentral', 'homer': 'Southcentral',
    'anchorage': 'Southcentral', 'kodiak': 'Gulf Coast', 'seward': 'Gulf Coast',
    'wasilla': 'Mat-Su', 'palmer': 'Mat-Su', 'mat-su': 'Mat-Su', 'matanuska': 'Mat-Su',
    'big lake': 'Mat-Su', 'houston': 'Mat-Su', 'sutton': 'Mat-Su',
    'fairbanks': 'Interior', 'delta': 'Interior', 'north pole': 'Interior', 'nenana': 'Interior',
    'juneau': 'Southeast', 'sitka': 'Southeast', 'ketchikan': 'Southeast', 'wrangell': 'Southeast',
    'petersburg': 'Southeast', 'skagway': 'Southeast', 'haines': 'Southeast',
    'bethel': 'Western Alaska', 'nome': 'Western Alaska', 'dillingham': 'Western Alaska',
    'kotzebue': 'North Slope', 'barrow': 'North Slope', 'utqiagvik': 'North Slope',
    'valdez': 'Gulf Coast', 'cordova': 'Gulf Coast', 'glennallen': 'Interior',
    'tok': 'Interior', 'mcgrath': 'Western Alaska', 'unalaska': 'Southwest',
    'king salmon': 'Southwest', 'sand point': 'Southwest', 'cold bay': 'Southwest',
}

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def load_data():
    if os.path.exists(FILE_PATH):
        try:
            with open(FILE_PATH, 'r') as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_data(data):
    os.makedirs('data', exist_ok=True)
    os.makedirs('public/data', exist_ok=True)
    with open(FILE_PATH, 'w') as f:
        json.dump(data, f, indent=2)
    try:
        os.makedirs(os.path.dirname(PUBLIC_PATH), exist_ok=True)
        shutil.copy2(FILE_PATH, PUBLIC_PATH)
    except Exception:
        pass  # PUBLIC_PATH only exists locally, not in CI


def generate_hash(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def infer_region(text):
    lower = text.lower()
    for keyword, region in REGION_MAP.items():
        if keyword in lower:
            return region
    return 'Statewide'


# ---------------------------------------------------------------------------
# Entity extraction — the intelligence layer
# ---------------------------------------------------------------------------

def extract_entities(dispatch_text: str, incident_type: str = '') -> dict:
    """
    Parse the raw dispatch narrative and return a structured entities dict:
      suspects, charges, bac, facility, bail, outcome,
      incident_datetime, co_agencies, address_detail
    """
    text = dispatch_text or ''
    entities = {
        'suspects': [],
        'charges': [],
        'bac': None,
        'facility': None,
        'bail': {'status': 'unknown', 'amount': None},
        'outcome': 'unknown',
        'incident_datetime': None,
        'co_agencies': [],
        'address_detail': None,
        'is_missing_person': False,
    }

    # --- Suspects (name + optional age) ---
    # Pattern A: "Firstname [Middle] Lastname (age)"
    for m in re.finditer(
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})\s*\((\d{1,3})\)',
        text
    ):
        name = m.group(1).strip()
        age = int(m.group(2))
        if age < 5 or age > 100:
            continue  # skip non-age numbers like case refs
        entities['suspects'].append({'name': name, 'age': age})

    # Pattern B: "X-year-old Firstname [Middle] Lastname"
    for m in re.finditer(
        r'(\d{1,3})-year-old\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})',
        text
    ):
        age = int(m.group(1))
        name = m.group(2).strip()
        if age < 5 or age > 100:
            continue
        if not any(s['name'] == name for s in entities['suspects']):
            entities['suspects'].append({'name': name, 'age': age})

    # Pattern C: "age YOA" pattern e.g. "William Ogan 42 YOA"
    for m in re.finditer(
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})\s+(\d{1,3})\s+YOA',
        text
    ):
        name = m.group(1).strip()
        age = int(m.group(2))
        if not any(s['name'] == name for s in entities['suspects']):
            entities['suspects'].append({'name': name, 'age': age})

    # --- spaCy Auto-NER Fallback & Vehicles ---
    entities['vehicles'] = []
    entities['drugs_weapons'] = []
    
    if nlp is not None and len(text) > 20:
        doc = nlp(text)
        
        # 1. Catch missed Suspects/Victims (PERSON)
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                clean_name = ent.text.strip().replace('\n', ' ')
                # Ignore very short or single lower case acronyms
                if len(clean_name) > 4 and clean_name.istitle():
                    if not any(clean_name in s['name'] or s['name'] in clean_name for s in entities['suspects']):
                        entities['suspects'].append({'name': clean_name, 'age': None})
            
            # 2. Extract specific Locations missing from specific regex
            elif ent.label_ == "GPE" or ent.label_ == "LOC":
                loc = ent.text.strip()
                if not entities['address_detail']:
                    entities['address_detail'] = loc
                    
        # 3. Look for specific Vehicles explicitly (Snowmachines, ATVs, Trucks)
        for token in doc:
            word = token.text.lower()
            if word in ["truck", "sedan", "suv", "snowmachine", "atv", "motorcycle", "skiff", "vessel"]:
                # Grab a mini phrase like "Yamaha snowmachine" or "Ford F-150 truck"
                vehicle_str = text[max(0, token.idx - 15) : token.idx + len(word)].strip()
                vehicle_str = re.sub(r'^[^A-Z]*', '', vehicle_str) # Strip leading garbage
                if len(vehicle_str) > 3 and vehicle_str not in entities['vehicles']:
                    entities['vehicles'].append(vehicle_str)
                    
        # 4. Look for Contraband (Drugs & Weapons)
        contraband_keys = ["meth", "methamphetamine", "heroin", "fentanyl", "cocaine", "firearm", "handgun", "rifle", "shotgun"]
        for word in contraband_keys:
            if re.search(r'\b' + word + r'\b', text.lower()):
                if word not in entities['drugs_weapons']:
                    entities['drugs_weapons'].append(word)

    # Deduplicate suspects
    seen = set()
    unique_suspects = []
    for s in entities['suspects']:
        if s['name'] not in seen:
            seen.add(s['name'])
            unique_suspects.append(s)
    entities['suspects'] = unique_suspects

    # --- BAC (breath alcohol content) ---
    bac_m = re.search(r'(\d*\.\d+)\s*Br?AC', text, re.I)
    if bac_m:
        try:
            entities['bac'] = float(bac_m.group(1))
        except ValueError:
            pass

    # --- Charges ---
    charge_patterns = [
        r'(?:charges?\s+of|arrested\s+for|arrested\s+on\s+charges?\s+of|'
        r'cited\s+for|charged\s+with|remanded\s+for)\s+'
        r'([^.!?\n]{3,200}?)(?:\.\s|\band\s+(?:was\s+)?(?:transport|remand|taken|held|booked)|$)',
    ]
    for pattern in charge_patterns:
        m = re.search(pattern, text, re.I)
        if m:
            raw = m.group(1).strip().rstrip(',. ')
            # split on ", " and " and "
            parts = re.split(r',\s*(?:and\s+)?|\s+and\s+', raw)
            entities['charges'] = [p.strip().rstrip('.') for p in parts if len(p.strip()) > 2]
            break

    # --- Facility ---
    for code, full_name in FACILITY_MAP.items():
        if re.search(r'\b' + re.escape(code) + r'\b', text, re.I):
            entities['facility'] = {'code': code, 'name': full_name}
            break

    # --- Bail ---
    if re.search(r'\bno\s+bail\b|\bwithout\s+bail\b', text, re.I):
        entities['bail'] = {'status': 'denied', 'amount': None}
    elif re.search(r'bail\s+(?:was\s+)?set\s+at\s+\$?([\d,]+)', text, re.I):
        m = re.search(r'bail\s+(?:was\s+)?set\s+at\s+\$?([\d,]+)', text, re.I)
        entities['bail'] = {'status': 'set', 'amount': m.group(1).replace(',', '') if m else None}
    elif re.search(r'\breleased\s+(?:on\s+recognizance|OR\b|without\s+bail|with\s+no\s+bail)', text, re.I):
        entities['bail'] = {'status': 'released_OR', 'amount': None}
    elif re.search(r'\bcitation\b|\bcited\b', text, re.I):
        entities['bail'] = {'status': 'cited_released', 'amount': None}

    # --- Outcome ---
    if re.search(r'\barrested\b', text, re.I):
        entities['outcome'] = 'arrested'
    elif re.search(r'\bsafely\s+(?:recovered|located|found|rescued)\b', text, re.I):
        entities['outcome'] = 'rescued'
    elif re.search(r'\bdeceased\b|\bdied\b|\bfatally\b|\bdeath\b', text, re.I):
        entities['outcome'] = 'fatal'
    elif re.search(r'\bcited\b|\bcitation\b', text, re.I):
        entities['outcome'] = 'cited'
    elif re.search(r'\breleased\b', text, re.I):
        entities['outcome'] = 'released'
    elif re.search(r'\binvestigation\s+(?:is\s+)?ongoing\b|\bunder\s+investigation\b', text, re.I):
        entities['outcome'] = 'investigation_ongoing'
    elif re.search(r'\breferred\b|\brefer\b', text, re.I):
        entities['outcome'] = 'referred'

    # --- Missing Person / SAR / AMBER Alert ---
    if re.search(r'\b(?:missing person|silver alert|amber alert|search and rescue|sar)\b', text, re.I):
        entities['is_missing_person'] = True

    # --- Incident datetime ---
    # "On M/D/YYYY at HHMM hours" or "On M/D/YYYY, at approximately HHMM hours"
    inc_dt_m = re.search(
        r'[Oo]n\s+(\d{1,2}/\d{1,2}/\d{4})[,\s]+at\s+(?:approximately\s+)?(\d{3,4})\s+hours?',
        text
    )
    if inc_dt_m:
        date_str = inc_dt_m.group(1)
        time_str = inc_dt_m.group(2).zfill(4)
        try:
            hour = int(time_str[:2])
            minute = int(time_str[2:])
            dt = datetime.strptime(date_str, '%m/%d/%Y').replace(
                hour=hour, minute=minute, tzinfo=timezone.utc
            )
            entities['incident_datetime'] = dt.isoformat()
        except ValueError:
            pass

    # --- Co-agencies ---
    agency_m = re.search(
        r'with\s+(?:the\s+)?assistance\s+of\s+([^.!?\n]{5,200})',
        text, re.I
    )
    if agency_m:
        raw = agency_m.group(1).strip().rstrip('.')
        agencies = re.split(r',\s*|\s+and\s+', raw)
        entities['co_agencies'] = [a.strip() for a in agencies if len(a.strip()) > 3]

    # --- Specific address detail ---
    addr_m = re.search(
        r'(?:on|at|near)\s+([A-Z][a-zA-Z0-9 ]+(?:Drive|Road|Rd|Street|St|Avenue|Ave|Way|'
        r'Loop|Highway|Hwy|Boulevard|Blvd|Lane|Ln|Circle|Place|Trail|Path)[^,\n.]{0,40})',
        text, re.I
    )
    if addr_m:
        entities['address_detail'] = addr_m.group(1).strip()
    else:
        # Highway mile marker
        mile_m = re.search(
            r'(?:near\s+)?mile\s+(\d+(?:\.\d+)?)\s+(?:of\s+)?(?:the\s+)?([A-Z][a-zA-Z ]+(?:Highway|Hwy))',
            text, re.I
        )
        if mile_m:
            entities['address_detail'] = f"Mile {mile_m.group(1)} {mile_m.group(2).strip()}"

    return entities


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

def get_dispatch_date_param(dt=None):
    if dt is None:
        dt = datetime.now()
    date_str = dt.strftime('%-m/%-d/%Y') + ' 12:00:00 AM'
    return {'dateReceived': date_str}


def scrape_date(dt=None):
    """Fetch and parse all incidents for one date. Returns list of incident dicts."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("⚠ BeautifulSoup4 not installed: pip install beautifulsoup4 requests")
        return []

    params = get_dispatch_date_param(dt)
    date_label = (dt or datetime.now()).strftime('%Y-%m-%d')
    print(f"  Fetching AST dispatch for {date_label}...")

    try:
        resp = requests.get(
            DISPATCH_URL, params=params,
            headers={'User-Agent': CHROME_UA}, timeout=15
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"  ✗ Failed to fetch dispatch for {date_label}: {e}")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    incidents = []
    seen_incidents = set()

    # Track current detachment as we walk the page
    current_detachment = 'General'

    def find_detachment_for_link(link_tag):
        """Walk backwards from the link to find the nearest detachment heading."""
        for parent in link_tag.parents:
            prev = parent.find_previous_sibling(['h3', 'h4'])
            if prev and ('detachment' in prev.get_text().lower() or
                        'bureau' in prev.get_text().lower() or
                        'wildlife' in prev.get_text().lower()):
                return prev.get_text().strip()
        return 'General'

    incident_links = soup.find_all('a', href=re.compile(r'DisplayIncident\?incidentNumber=AK'))

    for link in incident_links:
        try:
            inc_match = re.search(r'incidentNumber=(AK\d+)', link['href'])
            if not inc_match:
                continue
            inc_id = inc_match.group(1)
            if inc_id in seen_incidents:
                continue
            seen_incidents.add(inc_id)

            # Find parent container — walk up for more context
            parent = link.find_parent(['li', 'div', 'tr', 'td'])
            if not parent:
                parent = link.parent
            for _ in range(4):
                if parent and len(parent.get_text(strip=True)) < 120:
                    parent = parent.find_parent(['li', 'div', 'section'])
                else:
                    break

            full_text = parent.get_text(separator='\n', strip=True) if parent else ''

            # Detachment
            detachment = find_detachment_for_link(link)

            # Extract fields
            location_m = re.search(r'Location[:\s]+([^\n]+)', full_text, re.I)
            type_m = re.search(r'Type[:\s]+([^\n]+)', full_text, re.I)
            dispatch_m = re.search(
                r'Dispatch Text[:\s]+([\s\S]+?)(?:Posted on|$)', full_text, re.I
            )
            posted_m = re.search(r'Posted on ([^\n]+)', full_text, re.I)

            location = location_m.group(1).strip() if location_m else 'Alaska'
            incident_type = type_m.group(1).strip() if type_m else 'Incident'
            dispatch_text = dispatch_m.group(1).strip() if dispatch_m else full_text[:600]
            posted_raw = posted_m.group(1).strip() if posted_m else ''

            # Clean dispatch text
            dispatch_text = re.sub(r'\s+', ' ', dispatch_text).strip()
            if not dispatch_text or len(dispatch_text) < 20:
                continue

            # Parse original DPS "Posted on" timestamp
            posted_ts = None
            officer_id = None
            if posted_raw:
                # Extract officer ID "by DPS\kdanderson"
                officer_m = re.search(r'by\s+DPS\\+(.+?)$', posted_raw, re.I)
                if officer_m:
                    officer_id = officer_m.group(1).strip()
                clean_posted = re.sub(r'\s+by\s+.*$', '', posted_raw, flags=re.I).strip()
                for fmt in ('%m/%d/%Y %I:%M:%S %p', '%m/%d/%Y %H:%M:%S', '%m/%d/%Y'):
                    try:
                        posted_ts = datetime.strptime(clean_posted, fmt).replace(
                            tzinfo=timezone.utc
                        ).isoformat()
                        break
                    except ValueError:
                        continue
            if not posted_ts:
                posted_ts = datetime.now(timezone.utc).isoformat()

            # --- Entity extraction ---
            entities = extract_entities(dispatch_text, incident_type)
            entities['detachment'] = detachment
            entities['officer_id'] = officer_id

            # Compute reporting latency if we have both datetimes
            if entities.get('incident_datetime') and posted_ts:
                try:
                    inc_dt = datetime.fromisoformat(entities['incident_datetime'])
                    post_dt = datetime.fromisoformat(posted_ts)
                    delta_hours = (post_dt - inc_dt).total_seconds() / 3600
                    entities['reporting_latency_hours'] = round(delta_hours, 1)
                except Exception:
                    pass

            region = infer_region(f"{location} {dispatch_text}")
            title = f"AST {incident_type}: {location} [{inc_id}]"
            article_url = f"{BASE_URL}/Home/Search?incidentNumber={inc_id}"
            
            # Smart Geocoding Engine Hook
            coords = None
            
            # 1. Attempt precise highway mile marker geocoding
            # Check address_detail first, then fallback to entire dispatch_text
            text_to_check = f"{entities.get('address_detail', '')} {dispatch_text}"
            mile_m = re.search(r'(?:near\s+)?Mile\s+([\d.]+)\s+(?:of\s+)?(?:the\s+)?([A-Z][a-zA-Z ]+(?:Highway|Hwy))', text_to_check, re.I)
            if mile_m:
                coords = geocode_milemarker(mile_m.group(2).strip(), float(mile_m.group(1)))
                print(f"  [GEO_MILEPOST] matched '{mile_m.group(0)}' -> coords: {coords}")

            # 2. Fall back to generic regional/city text geocoding
            if not coords:
                coords = geocode_text(f"{location} {dispatch_text}")

            # Apply specific missing person escalating tags
            impact_score = 60
            urgency = 'background'
            if entities.get('is_missing_person') or incident_type.lower() in ['missing person', 'search and rescue', 'silver alert', 'amber alert']:
                impact_score = 90
                urgency = 'now'
                topic = 'Missing Person / Tracker'
                category = 'Emergency'
            else:
                topic = incident_type
                category = 'Safety'

            item = {
                'hash':              generate_hash(inc_id),
                'id':                inc_id,
                'source':            'Alaska State Troopers',
                'category':          category,
                'title':             title,
                'link':              article_url,
                'sourceUrl':         BASE_URL,
                'articleUrl':        article_url,
                'lat':               coords[0] if coords else None,
                'lng':               coords[1] if coords else None,
                'favicon':           'https://www.dps.alaska.gov/favicon.ico',
                'location':          location,
                'incident_type':     incident_type,
                'summary':           dispatch_text[:800],
                'dataTag':           f"[Region: {region}] [Category: {category}]",
                'sourceAttribution': 'Source: Alaska State Troopers Daily Dispatch',
                'section':           'Safety',
                'sourceLean':        'neutral',
                'topic':             topic,
                'impactScore':       impact_score,
                'urgency':           urgency,
                'timestamp':         posted_ts,
                'scraped_at':        datetime.now(timezone.utc).isoformat(),
                'posted':            posted_raw,
                'entities':          entities,  # ← full structured data
            }
            incidents.append(item)

        except Exception as e:
            print(f"  ✗ Error parsing incident: {e}")
            continue

    return incidents


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def scrape_ast_dispatches(days_back=6):
    """
    Scrape the last N+1 days of AST dispatches.
    Default: 7 days (days_back=6) to ensure thorough backfill.
    The DPS site only shows 7 days; this keeps us fully covered.
    """
    print("=" * 60)
    print("Alaska State Trooper Daily Dispatch Scraper (Enhanced)")
    print("=" * 60)

    existing = load_data()
    # Re-extract entities for existing records that are missing them
    existing_dict = {item.get('hash'): item for item in existing}
    existing_hashes = set(existing_dict.keys())

    total_new = 0
    total_updated = 0

    for day_offset in range(days_back + 1):
        target_date = datetime.now() - timedelta(days=day_offset)
        incidents = scrape_date(target_date)

        for item in incidents:
            h = item.get('hash')
            if not h:
                continue
            if h not in existing_hashes:
                existing_dict[h] = item
                existing_hashes.add(h)
                total_new += 1
            else:
                # Update entities on existing records (re-extract improvement)
                existing_dict[h]['entities'] = item['entities']
                existing_dict[h]['timestamp'] = item['timestamp']
                existing_dict[h]['favicon'] = item.get('favicon', '')
                total_updated += 1

    # Flatten, sort newest first, cap at 15000 records to allow long-term growth
    merged = sorted(
        existing_dict.values(),
        key=lambda x: x.get('timestamp', ''),
        reverse=True
    )[:15000]

    save_data(merged)

    # --- Validation summary ---
    print(f"\n{'='*60}")
    print(f"✓ NEW records added:     {total_new}")
    print(f"✓ Existing re-enriched:  {total_updated}")
    print(f"✓ Total in database:     {len(merged)}")

    # Spot-check entity extraction quality
    with_suspects  = sum(1 for r in merged if r.get('entities', {}).get('suspects'))
    with_charges   = sum(1 for r in merged if r.get('entities', {}).get('charges'))
    with_facility  = sum(1 for r in merged if r.get('entities', {}).get('facility'))
    with_outcome   = sum(1 for r in merged if r.get('entities', {}).get('outcome') not in ('unknown', None))
    with_bail      = sum(1 for r in merged if r.get('entities', {}).get('bail', {}).get('status') not in ('unknown', None))
    with_bac       = sum(1 for r in merged if r.get('entities', {}).get('bac'))
    with_inc_dt    = sum(1 for r in merged if r.get('entities', {}).get('incident_datetime'))

    print(f"\nEntity extraction coverage (of {len(merged)} records):")
    print(f"  Suspects identified:  {with_suspects:>4}  ({100*with_suspects//max(len(merged),1):>3}%)")
    print(f"  Charges parsed:       {with_charges:>4}  ({100*with_charges//max(len(merged),1):>3}%)")
    print(f"  Facility extracted:   {with_facility:>4}  ({100*with_facility//max(len(merged),1):>3}%)")
    print(f"  Outcome determined:   {with_outcome:>4}  ({100*with_outcome//max(len(merged),1):>3}%)")
    print(f"  Bail status parsed:   {with_bail:>4}  ({100*with_bail//max(len(merged),1):>3}%)")
    print(f"  BAC extracted:        {with_bac:>4}  ({100*with_bac//max(len(merged),1):>3}%)")
    print(f"  Incident datetime:    {with_inc_dt:>4}  ({100*with_inc_dt//max(len(merged),1):>3}%)")
    print("=" * 60)


if __name__ == '__main__':
    scrape_ast_dispatches(days_back=6)
