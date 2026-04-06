#!/usr/bin/env python3
"""
Alaska Fisheries Fetcher
Pulls fisheries data from ADF&G, NOAA, and other sources.
Outputs structured JSON to data/fisheries.json

Sources:
  - ADF&G emergency orders and news RSS
  - NOAA Fisheries Alaska region
  - ADF&G regional updates (Bristol Bay, Cook Inlet, Southeast, PWS, Yukon)
"""

import json
import os
import re
import hashlib
import feedparser
from datetime import datetime, timezone

FISHERIES_FEEDS = [
    {"name": "ADF&G Commercial Fisheries", "url": "https://proxy.alaskaintel.com/rss/adfg-cf", "region": "Statewide"},
    {"name": "ADF&G Sport Fishing", "url": "https://proxy.alaskaintel.com/rss/adfg-sf", "region": "Statewide"},
    {"name": "NOAA Fisheries Alaska", "url": "https://fisheries.noaa.gov/region/alaska/rss", "region": "Statewide"},
    {"name": "North Pacific Fishery Mgmt Council", "url": "https://www.npfmc.org/feed", "region": "Statewide"},
    {"name": "SeafoodNews Alaska", "url": "https://seafoodnews.com/RSS/Alaska", "region": "Statewide"},
    {"name": "Fish Alaska Magazine", "url": "https://fishalaskamagazine.com/feed", "region": "Statewide"},
    {"name": "Pacific Maritime Magazine", "url": "https://pacmar.com/feed", "region": "Statewide"},
]

# Regional coordinates for map placement
REGION_COORDS = {
    "Bristol Bay": {"lat": 58.8, "lng": -158.5},
    "Cook Inlet": {"lat": 60.5, "lng": -151.5},
    "Southeast": {"lat": 57.0, "lng": -134.0},
    "Prince William Sound": {"lat": 60.7, "lng": -147.0},
    "Yukon River": {"lat": 63.5, "lng": -160.0},
    "Statewide": {"lat": 63.0, "lng": -152.0},
}

OUTPUT_PATH = os.path.join("data", "fisheries.json")


def generate_hash(title, link):
    return hashlib.md5(f"{title}|{link}".encode()).hexdigest()


def classify_fisheries_item(title, summary):
    """Classify fisheries item type."""
    text = f"{title} {summary}".lower()
    if any(w in text for w in ["emergency order", "eo ", "e.o."]):
        return "emergency_order"
    if any(w in text for w in ["closure", "closed", "restriction"]):
        return "closure"
    if any(w in text for w in ["opening", "opened", "opener"]):
        return "opening"
    if any(w in text for w in ["sonar", "count", "escapement"]):
        return "sonar_count"
    if any(w in text for w in ["harvest", "catch", "landings"]):
        return "harvest"
    if any(w in text for w in ["regulation", "rule", "management"]):
        return "regulation"
    return "update"


def detect_species(title, summary):
    """Detect fish species mentioned."""
    text = f"{title} {summary}".lower()
    species = []
    species_keywords = {
        "salmon": ["salmon", "sockeye", "chinook", "king salmon", "coho", "silver", "pink", "chum", "keta"],
        "halibut": ["halibut"],
        "crab": ["crab", "king crab", "tanner", "opilio", "bairdi"],
        "herring": ["herring"],
        "pollock": ["pollock"],
        "cod": ["cod", "pacific cod"],
        "sablefish": ["sablefish", "black cod"],
    }
    for species_name, keywords in species_keywords.items():
        if any(kw in text for kw in keywords):
            species.append(species_name)
    return species


def fetch_fisheries():
    """Fetch all fisheries feeds."""
    print("Fetching Alaska fisheries data...")

    items = []
    seen_hashes = set()

    for feed_info in FISHERIES_FEEDS:
        print(f"  Fetching: {feed_info['name']}...")
        try:
            parsed = feedparser.parse(feed_info["url"])

            if not parsed.entries:
                print(f"    ⚠️  No entries from {feed_info['name']}")
                continue

            for entry in parsed.entries[:15]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                summary = entry.get("summary", "").strip()

                if not title or not link:
                    continue

                item_hash = generate_hash(title, link)
                if item_hash in seen_hashes:
                    continue
                seen_hashes.add(item_hash)

                # Clean HTML from summary
                clean_summary = re.sub(r"<[^>]+>", " ", summary)
                clean_summary = re.sub(r"\s+", " ", clean_summary).strip()[:300]

                published_struct = entry.get("published_parsed") or entry.get("updated_parsed")
                if published_struct:
                    published_iso = datetime(
                        *published_struct[:6], tzinfo=timezone.utc
                    ).isoformat()
                else:
                    published_iso = datetime.now(timezone.utc).isoformat()

                coords = REGION_COORDS.get(feed_info["region"], REGION_COORDS["Statewide"])

                items.append({
                    "id": item_hash,
                    "title": title,
                    "link": link,
                    "summary": clean_summary,
                    "published": published_iso,
                    "source": feed_info["name"],
                    "region": feed_info["region"],
                    "type": classify_fisheries_item(title, clean_summary),
                    "species": detect_species(title, clean_summary),
                    "lat": coords["lat"],
                    "lng": coords["lng"],
                })

            entry_count = len(parsed.entries[:15])
            print(f"    ✓ {entry_count} entries")

        except Exception as e:
            print(f"    ✗ Error: {e}")

    # Sort by date, newest first
    items.sort(key=lambda x: x.get("published", ""), reverse=True)
    return items


def save_data(items):
    """Save fisheries data to JSON."""
    os.makedirs("data", exist_ok=True)

    # Summary stats
    region_counts = {}
    type_counts = {}
    all_species = set()
    for item in items:
        region = item["region"]
        region_counts[region] = region_counts.get(region, 0) + 1
        item_type = item["type"]
        type_counts[item_type] = type_counts.get(item_type, 0) + 1
        all_species.update(item.get("species", []))

    output = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "source": "ADF&G, NOAA, NPFMC",
        "source_url": "https://www.adfg.alaska.gov/",
        "summary": {
            "total_items": len(items),
            "by_region": region_counts,
            "by_type": type_counts,
            "species_mentioned": sorted(all_species),
        },
        "items": items,
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Saved {len(items)} fisheries items to {OUTPUT_PATH}")


def main():
    print("=" * 50)
    print("Alaska Fisheries Fetcher")
    print("=" * 50)

    items = fetch_fisheries()
    save_data(items)


if __name__ == "__main__":
    main()
