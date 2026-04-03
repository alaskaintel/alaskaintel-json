#!/usr/bin/env python3
"""
University of Alaska Grant Deadlines Scraper
Uses Playwright to render InfoReady SPA portals and extract active grant deadlines into AlaskaIntel signals.
"""

import json
import os
import hashlib
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

# Known active InfoReady portals for the UA system
UA_PORTALS = {
    "UAA": "https://uaa.infoready4.com/"
}

OUTPUT_FILE = os.path.join("data", "ua_grants.json")

def parse_date(date_str: str) -> str:
    """Attempts to parse varied InfoReady date formats into ISO 8601."""
    # Example format: "04/05/2026", "April 5, 2026"
    date_str = date_str.strip()
    if not date_str:
        return datetime.now(timezone.utc).isoformat()
    
    try:
        if "/" in date_str:
            d = datetime.strptime(date_str, "%m/%d/%Y")
        else:
            d = datetime.strptime(date_str, "%b %d, %Y")
        return d.replace(tzinfo=timezone.utc).isoformat()
    except Exception:
        pass
    return datetime.now(timezone.utc).isoformat()

def scrape_infoready():
    signals = []
    
    with sync_playwright() as p:
        # Use chromium
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()

        for campus, url in UA_PORTALS.items():
            print(f"Scraping {campus} InfoReady portal: {url}")
            try:
                page.goto(url, timeout=30000, wait_until="networkidle")
                
                # Wait for the DataTables or ag-grid to load
                page.wait_for_selector("table tbody tr", timeout=15000)
                
                # Extract rows
                rows = page.query_selector_all("table tbody tr")
                print(f"Found {len(rows)} grants listed.")
                
                for row in rows:
                    cols = row.query_selector_all("td")
                    if len(cols) < 3:
                        continue
                        
                    # Extract title and link
                    title_elem = cols[0].query_selector("a")
                    if not title_elem:
                        continue
                        
                    title = title_elem.inner_text().strip()
                    href = title_elem.get_attribute("href")
                    if href:
                        if href.startswith("/"):
                            href = url.rstrip("/") + href
                        elif href.startswith("#"):
                            href = url.rstrip("/") + "/" + href
                        
                    # Extract deadline (usually the last or second to last column)
                    # Let's just grab all column text to find the one that looks like a date
                    deadline_text = ""
                    for col in reversed(cols):
                        text = col.inner_text().strip()
                        if "/" in text or "202" in text:
                            deadline_text = text
                            break
                    
                    if not deadline_text:
                        deadline_text = cols[-1].inner_text().strip()

                    # Create a standard temporal signal from the grant deadline
                    published_iso = parse_date(deadline_text)
                    summary = f"Deadline: {deadline_text} | Internal Funding Opportunity from {campus}"
                    
                    hash_str = hashlib.md5(f"ua_grant_{campus}_{title}".encode()).hexdigest()
                    
                    signal = {
                        "title": f"[{campus} Grant] {title}",
                        "link": href or url,
                        "published": published_iso,
                        "source": f"University of Alaska ({campus})",
                        "category": "Education",
                        "summary": summary,
                        "hash": hash_str,
                        "type": "grant"
                    }
                    signals.append(signal)

            except Exception as e:
                print(f"Failed to scrape {campus}: {e}")
                
        browser.close()

    print(f"Parsed {len(signals)} total UA grants into signals.")

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(signals, f, indent=4)
        
    print(f"Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    scrape_infoready()
