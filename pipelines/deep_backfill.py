#!/usr/bin/env python3
"""
Deep Backfill Pagination Crawler
Bypasses the standard 50-item RSS limit by traversing `?paged=X` parameters
for all compatible WordPress and paginated CMS news feeds.
"""

import os
import json
import logging
import feedparser
import requests
import urllib3
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

# Import the massive feed list and core utilities from the main pipeline
from fetch_intel import (
    FEEDS, generate_hash, resolve_article_url, is_bad_rss_item, clean_text,
    build_fair_use_snippet, save_data, CHROME_UA
)

def process_paginated_feed(feed: dict, max_pages: int = 20) -> list:
    """ Crawl pages 2 through `max_pages` for a single feed """
    base_url = feed["url"]
    items = []
    
    headers = {"User-Agent": CHROME_UA}
    
    for page in range(2, max_pages + 1):
        if "?" in base_url:
            paged_url = f"{base_url}&paged={page}"
        else:
            paged_url = f"{base_url}?paged={page}"
            
        logging.info(f"Crawling deep feed: {paged_url}")
        try:
            r = requests.get(paged_url, headers=headers, timeout=10, verify=False)
            if r.status_code != 200:
                break # Reached the end of pagination (yields 404 or 400 usually)
                
            parsed = feedparser.parse(r.content)
            if not parsed.entries:
                break # Feed is empty, reached max depth natively
                
            for entry in parsed.entries:
                title = entry.get("title", "").strip()
                link = resolve_article_url(title, entry.get("link", ""))
                
                raw_summary = entry.get("summary", "")
                if "content" in entry and entry.content:
                    raw_summary = entry.content[0].value
                    
                if is_bad_rss_item(title, link, raw_summary):
                    continue
                    
                cleaned_summary = clean_text(raw_summary)
                desc = build_fair_use_snippet(cleaned_summary)
                
                try:
                    if "published_parsed" in entry and entry.published_parsed:
                        dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    else:
                        dt = datetime.now(timezone.utc)
                except Exception:
                    dt = datetime.now(timezone.utc)
                    
                hash_id = generate_hash(title, link)
                
                items.append({
                    "hash": hash_id,
                    "title": title,
                    "summary": desc,
                    "source": feed["name"],
                    "sourceUrl": feed.get("author", feed["name"]),
                    "articleUrl": link,
                    "url": link,
                    "timestamp": dt.isoformat(),
                    "topic": feed.get("category", "News"),
                    "section": feed.get("category", "News")
                })
        except Exception as e:
            logging.debug(f"Halted pagination on {base_url} at page {page}: {e}")
            break
            
    return items

def main():
    logging.info(f"Starting Deep Backfill for {len(FEEDS)} feeds...")
    all_deep_items = []
    
    # We use a threadpool to scrape multiple endpoints concurrently without blocking
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(process_paginated_feed, feed): feed for feed in FEEDS}
        for fut in as_completed(futures):
            feed = futures[fut]
            try:
                res = fut.result()
                if res:
                    logging.info(f"✓ Extracted {len(res)} historical items from {feed['name']}")
                    all_deep_items.extend(res)
            except Exception as e:
                logging.error(f"Failed to deep crawl {feed['name']}: {e}")
                
    logging.info(f"Deep crawl finished! Found {len(all_deep_items)} historical items.")
    
    if all_deep_items:
        # Load the massive latest JSON database from local and append
        data_path = os.path.join("..", "data", "latest_intel.json")
        try:
            with open(data_path, "r") as f:
                core_data = json.load(f)
        except OSError:
            core_data = []
            
        existing_hashes = {i.get("hash") for i in core_data if i.get("hash")}
        
        injected = 0
        for item in all_deep_items:
            if item["hash"] not in existing_hashes:
                core_data.append(item)
                existing_hashes.add(item["hash"])
                injected += 1
                
        if injected > 0:
            core_data.sort(key=lambda x: str(x.get("timestamp", "")), reverse=True)
            with open(data_path, "w") as f:
                json.dump(core_data, f, indent=2)
            logging.info(f"Successfully integrated {injected} completely new backfilled signals into latest_intel.json!")
        else:
            logging.info("We already have all these backfilled signals natively.")
            
if __name__ == "__main__":
    main()
