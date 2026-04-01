#!/usr/bin/env python3
"""
Official DPS Stolen Vehicles API Extractor
Connects to the Alaska State Troopers CSV endpoint.
Parses the current 3,000+ active stolen vehicle records statewide.
Cross-references the official Case IDs with our NLP extracted `ast_logs.json` database
to automatically attach exact geographic coordinations, locations, and narrative dispatch logs!

Saves output to: data/stolen_vehicles.json
"""

import os
import csv
import json
import logging
import requests
from io import StringIO
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from xml.dom import minidom

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

API_URL = "https://publicdatasets.dps.alaska.gov/api/StolenVehicles/download"
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'}

AST_LOGS_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'ast_logs.json')
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'stolen_vehicles.json')
TOC_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'stolen_vehicles_toc.json')
RSS_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'stolen_vehicles.xml')

import random

# Geocoding Dictionary for Reporting Agencies to map the 3,000 unlinked incidents!
AGENCY_COORDINATES = {
    "ANCHORAGE": (61.2181, -149.9003),
    "PALMER": (61.5997, -149.1128),
    "FAIRBANKS": (64.8378, -147.7164),
    "SOLDOTNA": (60.4878, -151.0583),
    "WASILLA": (61.5809, -149.4411),
    "JUNEAU": (58.3019, -134.4197),
    "ANCHOR POINT": (59.7767, -151.8314),
    "KENAI": (60.5544, -151.2583),
    "HOMER": (59.6425, -151.5483),
    "SEWARD": (60.1042, -149.4422),
    "NORTH POLE": (64.7511, -147.3494),
    "NENANA": (64.5619, -149.0967),
    "DELTA JUNCTION": (64.0378, -145.7319),
    "WAINWRIGHT": (64.8213, -147.6047),
    "AIRPORT": (61.1751, -149.9964),
    "KODIAK": (57.7900, -152.4072),
    "KETCHIKAN": (55.3422, -131.6461),
    "SITKA": (57.0531, -135.3300),
    "BETHEL": (60.7922, -161.7558),
    "NOME": (64.5011, -165.4064),
    "MAT SU": (61.5809, -149.4411)
}

def get_agency_coordinates(agency_name):
    """Fuzzy match agency name to city dict and add slight jitter so pins don't stack."""
    agency_name = agency_name.upper()
    for city, coords in AGENCY_COORDINATES.items():
        if city in agency_name:
            jitter_lat = random.uniform(-0.02, 0.02)
            jitter_lng = random.uniform(-0.02, 0.02)
            return (coords[0] + jitter_lat, coords[1] + jitter_lng)
    return None, None

def load_intelligence_datalake():
    """Load the master dispatch database to cross-reference Case IDs."""
    logging.info("Fetching master intelligence datalake via HTTP array...")
    try:
        r = requests.get("https://data.alaskaintel.com/ast_logs.json", timeout=15)
        if r.status_code != 200:
            logging.warning("Failed to fetch ast_logs.json! Cannot cross-reference geographic locations.")
            return {}
        
        data = r.json()
        lookup_table = {}
        for incident in data:
            case_id = incident.get('id')
            if case_id:
                lookup_table[case_id] = incident
        logging.info(f"Loaded {len(lookup_table)} intelligence signals from ast_logs.json for cross-referencing.")
        return lookup_table
    except Exception as e:
        logging.error(f"Error loading intelligence datalake: {e}")
        return {}

def fetch_and_process():
    logging.info(f"Connecting to official DPS API endpoint: {API_URL}")
    response = requests.get(API_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    
    csv_data = StringIO(response.text)
    reader = csv.DictReader(csv_data)
    # The columns in the official CSV often have leading spaces (e.g., ' Vin', ' MakeModel')
    # So we will strip the keys
    
    intelligence_lake = load_intelligence_datalake()
    
    stolen_vehicles = []
    geolocation_hits = 0
    
    for i, raw_row in enumerate(reader):
        dps_page = (i // 10) + 1
        
        # Clean the keys
        row = {k.strip(): v.strip() for k, v in raw_row.items() if k}
        
        vin = row.get('Vin', '')
        plate = row.get('License', '')
        agency = row.get('Agency', '')
        year = row.get('PropertyModelYear', '')
        make_model = row.get('MakeModel', '')
        style = row.get('Style', '')
        color = row.get('Color', '')
        state = row.get('State', '')
        case_id = row.get('Case', '')
        date_str = row.get('Date', '')
        record_type = row.get('Type', 'Vehicle')
        
        # Build the structured API record gracefully handling edge cases
        if record_type.upper() == 'PLATE':
            title = f"Stolen License Plate"
            if plate: title += f" ({plate})"
        else:
            title_parts = []
            if year: title_parts.append(year)
            if make_model: title_parts.append(make_model)
            title = " ".join(title_parts) if title_parts else "Vehicle Theft"
            if color: title += f" ({color})"
            
        incident_cat = "Stolen Plate" if record_type.upper() == 'PLATE' else "Stolen Vehicle"
        
        # Default to None for geocoding
        lat = None
        lng = None
        location_str = None
        region = "Statewide"
        
        # Build robust summary
        sum_parts = []
        if year: sum_parts.append(f"Year: {year}")
        if color: sum_parts.append(f"Color: {color}")
        if style: sum_parts.append(f"Style: {style}")
        if state: sum_parts.append(f"State: {state}")
        if plate: sum_parts.append(f"Plate: {plate}")
        if vin: sum_parts.append(f"VIN: {vin}")
        summary = " | ".join(sum_parts) if sum_parts else "No additional vehicle context provided."
        
        entities = {
            'suspects': [],
            'outcome': 'investigation_ongoing',
            'vin': vin,
            'plate': plate,
            'year': year,
            'make_model': make_model,
            'style': style,
            'color': color,
            'jurisdiction': agency,
            'charges': [],
            'dps_page': dps_page
        }
        
        # ─── THE DATA MERGE ───────────────────────────────────────────────────
        # Cross reference the official case ID to see if we possess the raw intelligence!
        if case_id and case_id in intelligence_lake:
            intel = intelligence_lake[case_id]
            lat = intel.get('lat')
            lng = intel.get('lng')
            if lat and lng:
                geolocation_hits += 1
                
            location_str = intel.get('location')
            summary = intel.get('summary', summary) + f"\n\nVehicle Trace Matrix:\nYear: {year} | Color: {color} | Style: {style} | Plate: {plate}"
            
            # Inherit structured extraction points
            inc_entities = intel.get('entities', {})
            entities['dispatch_narrative'] = intel.get('summary', '')
            entities['suspects'] = inc_entities.get('suspects', [])
            entities['outcome'] = inc_entities.get('outcome', 'unknown')
            entities['address_detail'] = inc_entities.get('address_detail')
            
            # Extract Region from dataTag
            data_tag = intel.get('dataTag', '')
            import re
            rm = re.search(r'Region:\s([^\]]+)', data_tag)
            if rm:
                region = rm.group(1)
                
            # Override title to include location if known
            if location_str:
                title = f"{title} — {location_str}"
        
        # ─── FALLBACK GEOCODING ─────────────────────────────────────────────
        # If no precise coordinate was found, use the reporting agency city
        if not lat or not lng:
            lat, lng = get_agency_coordinates(agency)
            if lat and lng and not location_str:
                # Set a generic region string for the map popup
                location_str = agency

        # Attempt to parse date
        timestamp = datetime.now(timezone.utc).isoformat()
        if date_str:
            try:
                dt = datetime.strptime(date_str, '%m/%d/%Y')
                timestamp = dt.replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass
                
        record = {
            'hash':              f"stolen_{case_id}_{vin}",
            'id':                case_id,
            'source':            agency,
            'category':          'Stolen Vehicle',
            'title':             title,
            'link':              'https://hotsheets.dps.alaska.gov/AST/Stolen-Vehicle-Hot-Sheet',
            'sourceUrl':         'https://publicdatasets.dps.alaska.gov',
            'articleUrl':        'https://hotsheets.dps.alaska.gov/AST/Stolen-Vehicle-Hot-Sheet',
            'lat':               lat,
            'lng':               lng,
            'favicon':           'https://www.dps.alaska.gov/favicon.ico',
            'location':          location_str,
            'incident_type':     incident_cat,
            'summary':           summary,
            'dataTag':           f"[Region: {region}] [Category: Hot Sheet]",
            'sourceAttribution': 'Source: Alaska DPS Database',
            'section':           'Safety',
            'sector':            'safety',
            'urgency':           'soon',
            'impactScore':       85,
            'sourceLean':        'neutral',
            'topic':             'Stolen Vehicle',
            'timestamp':         timestamp,
            'scraped_at':        datetime.now(timezone.utc).isoformat(),
            'posted':            date_str,
            'entities':          entities,
        }
        stolen_vehicles.append(record)
        
    # Sort chronologically, newest first
    stolen_vehicles.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(stolen_vehicles, f, indent=2)
        
    # Table of Contents Pagination Mapping
    toc = {}
    for vehicle in stolen_vehicles:
        page = vehicle['entities'].get('dps_page', 1)
        if page not in toc:
            toc[page] = []
        toc[page].append({
            'id': vehicle['id'],
            'title': vehicle['title'],
            'date': vehicle['posted'],
            'agency': vehicle['source']
        })
        
    with open(TOC_OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(toc, f, indent=2)
        
    generate_rss(stolen_vehicles, RSS_OUTPUT_PATH)
        
    logging.info("=" * 60)
    logging.info(f"Target Acquired:  {len(stolen_vehicles)} total active stolen vehicles")
    logging.info(f"Data-Merge Map:   {geolocation_hits} precise coordinate connections established via Daily Dispatch cross-link")
    logging.info(f"Output Generated: {OUTPUT_PATH}")
    logging.info(f"RSS Generated:    {RSS_OUTPUT_PATH}")
    logging.info("=" * 60)

def generate_rss(vehicles, filepath):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "AlaskaIntel Stolen Vehicles"
    ET.SubElement(channel, "link").text = "https://www.alaskaintel.com/stolen-vehicles"
    ET.SubElement(channel, "description").text = "Live active stolen vehicle bulletins from Alaska DPS."
    
    for v in vehicles[:150]: # Limit RSS to newest 150
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = v.get("title", "Stolen Vehicle")
        ET.SubElement(item, "link").text = v.get("link", "https://hotsheets.dps.alaska.gov/AST/Stolen-Vehicle-Hot-Sheet")
        ET.SubElement(item, "description").text = v.get("summary", "")
        ET.SubElement(item, "pubDate").text = v.get("timestamp", "")
        ET.SubElement(item, "guid").text = v.get("id", "")
        
    xmlstr = minidom.parseString(ET.tostring(rss)).toprettyxml(indent="  ")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(xmlstr)

if __name__ == "__main__":
    fetch_and_process()
