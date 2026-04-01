#!/usr/bin/env python3
"""
Alaska Legislature Fetcher
Pulls bill status, session info, and committee activity from the
Alaska Legislature website and RSS feed.
Outputs structured JSON to data/legislature.json

Sources:
  - Alaska Legislature RSS: https://akleg.gov/basis/rss.asp
  - Alaska Legislature API: https://www.akleg.gov/basis/api
"""

import json
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

OUTPUT_PATH = os.path.join("data", "legislature.json")

# Juneau coordinates for map placement
JUNEAU_LAT = 58.3005
JUNEAU_LNG = -134.4197

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"}

def fetch_legislature_html():
    """Fetch latest legislature updates by parsing the hidden daily Actions endpoint over a 3-day window."""
    print("Fetching Alaska Legislature daily actions...")
    items = []
    
    # Establish rolling 3-day window (Today, Yesterday, 2 days ago)
    target_dates = [
        datetime.now(timezone.utc),
        datetime.now(timezone.utc) - timedelta(days=1),
        datetime.now(timezone.utc) - timedelta(days=2)
    ]
    
    for target_date in target_dates:
        date_str = target_date.strftime("%m/%d/%Y")
        url = f"https://www.akleg.gov/basis/Bill/Actions?Date={date_str}&type=B&chamber=Both"
        
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                print(f"  ⚠️  HTTP {resp.status_code} for {date_str}")
                continue
                
            soup = BeautifulSoup(resp.text, 'html.parser')
            rows = soup.find_all('tr')
            
            current_bill = None
            current_sponsor = None
            current_title = None
            current_status = None
            
            for row in rows:
                classes = row.get('class', [])
                
                # Check for Bill Header row (e.g. <tr class="House"> or <tr class="Senate">)
                if 'House' in classes or 'Senate' in classes:
                    cols = row.find_all('td')
                    if len(cols) >= 6:
                        bill_text = cols[0].get_text(separator=" ", strip=True)
                        current_bill = " ".join(bill_text.split())
                        current_title = cols[1].get_text(separator=" ", strip=True)
                        current_sponsor = cols[2].get_text(separator=" ", strip=True).replace("\n", "").strip()
                        current_status = cols[4].get_text(separator=" ", strip=True)
                
                # Check for the action row (e.g. <tr class="actionRow">)
                elif 'actionRow' in classes and current_bill:
                    cols = row.find_all('td')
                    if len(cols) >= 6:
                        action_summary = cols[1].get_text(separator=" ", strip=True)
                        if action_summary:
                            items.append({
                                "title": f"[{current_bill}] {current_title}",
                                "link": f"https://www.akleg.gov/basis/Bill/Detail/34?Root={current_bill.replace(' ', '')}",
                                "summary": f"{action_summary} (Status: {current_status}, Sponsor: {current_sponsor})",
                                "published": target_date.isoformat(),
                                "bill_number": current_bill,
                                "type": classify_item(action_summary),
                            })
                            
        except Exception as e:
            print(f"  ⚠️  Scrape error for {date_str}: {e}")
            
    print(f"  Found {len(items)} legislative actions across 3 days.")
    
    # Sort so newest items (today) appear first, though they might all have the same day timestamp
    return items

def classify_item(summary):
    """Classify legislature item by type based on the text."""
    summary_lower = summary.lower()
    if any(w in summary_lower for w in ["committee", "hearing", "referred to"]):
        return "committee"
    if any(w in summary_lower for w in ["floor session", "transmitting", "read the first time"]):
        return "floor"
    if any(w in summary_lower for w in ["signed", "vetoed", "enacted", "effective", "governor"]):
        return "executive"
    if any(w in summary_lower for w in ["introduced", "first reading"]):
        return "introduction"
    if any(w in summary_lower for w in ["passed", "approved", "adopted"]):
        return "passage"
    if any(w in summary_lower for w in ["amendment", "amended", "cosponsor", "cs "]):
        return "amendment"
    return "general"


def fetch_session_info():
    """Fetch current session information."""
    print("Fetching session information...")

    session = {
        "name": "34th Alaska Legislature",
        "session": "First Session",
        "year": datetime.now().year,
        "status": "in_session",
        "url": "https://www.akleg.gov/",
    }

    # Try to get session status from the website
    try:
        resp = requests.get("https://www.akleg.gov/", headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            text = resp.text.lower()
            if "second session" in text:
                session["session"] = "Second Session"
            if "special session" in text:
                session["session"] = "Special Session"
                session["status"] = "special_session"
            if "35th" in text:
                session["name"] = "35th Alaska Legislature"
            print(f"  ✓ Session: {session['name']} — {session['session']}")
        else:
            print(f"  ⚠️  Could not reach akleg.gov (HTTP {resp.status_code})")
    except Exception as e:
        print(f"  ⚠️  Session info error: {e}")

    return session


def save_data(items, session):
    """Save legislature data to JSON."""
    os.makedirs("data", exist_ok=True)

    # Count by type
    type_counts = {}
    for item in items:
        t = item["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    bills_mentioned = [i["bill_number"] for i in items if i["bill_number"]]

    output = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "source": "Alaska Legislature (BASIS)",
        "source_url": "https://www.akleg.gov/",
        "session": session,
        "summary": {
            "total_updates": len(items),
            "type_breakdown": type_counts,
            "bills_mentioned": list(set(bills_mentioned)),
        },
        "location": {
            "name": "Alaska State Capitol, Juneau",
            "lat": JUNEAU_LAT,
            "lng": JUNEAU_LNG,
        },
        "items": items,
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Saved {len(items)} legislature items to {OUTPUT_PATH}")
    if bills_mentioned:
        print(f"  Bills tracked: {', '.join(list(set(bills_mentioned))[:10])}")


def main():
    print("=" * 50)
    print("Alaska Legislature Fetcher")
    print("=" * 50)

    items = fetch_legislature_html()
    session = fetch_session_info()
    save_data(items, session)


if __name__ == "__main__":
    main()
