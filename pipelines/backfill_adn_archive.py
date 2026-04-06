#!/usr/bin/env python3
"""
Wayback Machine Historical Backfill Pipeline — Anchorage Daily News (ADN)
==========================================================================
Queries the archive.org CDX API for all HTML-type snapshots of adn.com
article pages from 1997 to the present, downloads the raw archived DOMs,
extracts structured intelligence signals, and appends them to the shared
latest_intel.json pipeline used by alaskaintel.com dashboards.

Usage:
    cd alaskaintel-data/scripts
    python3 backfill_adn_archive.py                        # full sweep 1997-today
    python3 backfill_adn_archive.py --from 1997 --to 2005  # year-range subset
    python3 backfill_adn_archive.py --limit 500            # cap snapshots (testing)

Output:
    data/adn_archive.json      — dedicated ADN archive store (not mixed with AST)
    data/latest_intel.json     — appended live after each checkpoint

Strategy:
    Era 1 (1997-2009)  → adn.com/* with broad path sweep, heuristic HTML parse
    Era 2 (2010-2019)  → article URL patterns /2010/, /2011/ ... /2019/
    Era 3 (2020-today) → modern arcgis-based article slugs /20XX/XX/XX/
"""

import sys
import os
import re
import json
import time
import hashlib
import argparse
from datetime import datetime, timezone
from typing import List, Dict, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
CDX_API       = "http://web.archive.org/cdx/search/cdx"
ADN_ARCHIVE   = os.path.join("data", "adn_archive.json")
INTEL_FILE    = os.path.join("data", "latest_intel.json")

# Archive.org CDX daily collapse token — one snapshot per page per day
DAILY_COLLAPSE = "timestamp:8"

# Polite crawl delay (archive.org ToS asks for ≥1 s between requests)
CRAWL_DELAY   = 1.5

# Minimum article body length before we discard a DOM as empty/nav-only
MIN_ARTICLE_BYTES = 400

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

# ─────────────────────────────────────────────────────────────────────────────
# Era-based URL path targets for the CDX sweep
# ADN has changed CMSes multiple times; each era has distinct URL patterns.
# ─────────────────────────────────────────────────────────────────────────────
CDX_TARGET_PATTERNS = [
    # Era 1 — pre-CMS flat HTML (1997-2004)
    "adn.com/stories/*",
    "adn.com/Alaska/*",
    "adn.com/nation/*",
    "adn.com/state/*",
    "adn.com/business/*",
    "adn.com/community/*",
    "adn.com/outdoors/*",
    "adn.com/oil/*",
    "adn.com/weather/*",
    "adn.com/crime/*",

    # Era 2 — Mid-CMS article slugs (2005-2015)
    "adn.com/article/*",
    "adn.com/article/ak-*",

    # Era 3 — Modern date-pathed slugs (2016-today)
    "adn.com/alaska-news/*",
    "adn.com/politics/*",
    "adn.com/environment/*",
    "adn.com/economy-business/*",
    "adn.com/nation-world/*",
    "adn.com/science/*",
    "adn.com/alaska-life/*",
    "adn.com/outdoors/*",
    "adn.com/crime-courts/*",
]

# Categories derived from the URL path slug
CATEGORY_MAP = {
    "crime": "Safety",
    "courts": "Safety",
    "politics": "Politics",
    "environment": "Environment",
    "oil": "Energy",
    "business": "Business",
    "economy": "Economy",
    "science": "Science",
    "alaska-news": "News",
    "alaska-life": "Regional",
    "outdoors": "Recreation",
    "weather": "Weather",
    "nation": "News",
    "community": "Regional",
    "stories": "News",
}

REGION_KEYWORDS = {
    "Mat-Su":          ["mat-su", "matanuska", "susitna", "wasilla", "palmer"],
    "Southcentral":    ["anchorage", "kenai", "soldotna", "homer", "cordova", "girdwood"],
    "Southeast":       ["juneau", "sitka", "ketchikan", "petersburg", "wrangell", "skagway"],
    "Interior":        ["fairbanks", "delta", "tok", "north pole"],
    "Western Alaska":  ["bethel", "nome", "dillingham", "kuskokwim"],
    "North Slope":     ["utqiagvik", "barrow", "north slope", "kotzebue"],
    "Gulf Coast":      ["kodiak", "valdez", "seward"],
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def make_hash(title: str, url: str) -> str:
    return hashlib.md5(f"{title}|{url}".encode()).hexdigest()


def infer_region(text: str) -> str:
    t = text.lower()
    for region, kws in REGION_KEYWORDS.items():
        if any(k in t for k in kws):
            return region
    return "Statewide"


def infer_category_from_url(url: str) -> str:
    url_l = url.lower()
    for kw, cat in CATEGORY_MAP.items():
        if f"/{kw}" in url_l:
            return cat
    return "News"


def ts_from_wayback(timestamp: str) -> str:
    """Convert Wayback 14-digit timestamp to ISO-8601 UTC string."""
    try:
        return datetime.strptime(timestamp[:14], "%Y%m%d%H%M%S").replace(
            tzinfo=timezone.utc
        ).isoformat()
    except Exception:
        return datetime.strptime(timestamp[:8], "%Y%m%d").replace(
            tzinfo=timezone.utc
        ).isoformat()


def load_json(path: str) -> list:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[!] Could not load {path}: {e}")
    return []


def save_json(path: str, data: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def checkpoint(archive_db: list, intel_db: list, new_items: list) -> None:
    """Append new items to both stores and write to disk."""
    archive_db.extend(new_items)
    intel_db.extend(new_items)

    # Sort both stores newest-first
    archive_db.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    intel_db.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    save_json(ADN_ARCHIVE, archive_db)
    save_json(INTEL_FILE, intel_db)
    print(f"   [»] Checkpoint — ADN archive: {len(archive_db)} | Intel: {len(intel_db)}")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 — CDX Manifest
# ─────────────────────────────────────────────────────────────────────────────
def build_cdx_manifest(year_from: int, year_to: int, limit: Optional[int]) -> List[Tuple[str, str]]:
    """
    Query archive.org CDX API across all ADN URL patterns.
    Returns a deduplicated list of (timestamp, original_url) tuples.
    """
    from_ts = f"{year_from}0101000000"
    to_ts   = f"{year_to}1231235959"

    manifest: List[Tuple[str, str]] = []
    seen_urls: Set[str] = set()

    print("\n" + "=" * 64)
    print("Phase 1 — CDX Manifest Builder")
    print(f"   Range : {year_from} → {year_to}")
    print("=" * 64)

    for pattern in CDX_TARGET_PATTERNS:
        print(f"\n[*] CDX sweep: {pattern}")
        params = {
            "url":      pattern,
            "output":   "json",
            "fl":       "timestamp,original",
            "filter":   ["statuscode:200", "mimetype:text/html"],
            "collapse": DAILY_COLLAPSE,
            "from":     from_ts,
            "to":       to_ts,
        }
        if limit:
            params["limit"] = str(limit)

        try:
            resp = requests.get(CDX_API, params=params, timeout=60,
                                headers={"User-Agent": CHROME_UA})
            data = resp.json()
            if len(data) > 1:
                batch = data[1:]   # strip header row
                added = 0
                for row in batch:
                    ts, url = row[0], row[1]
                    # Deduplicate by URL (ignoring protocol variant and port noise)
                    clean = re.sub(r"^https?://(?:www\.)?adn\.com:?\d*/", "", url).rstrip("/")
                    if clean not in seen_urls:
                        seen_urls.add(clean)
                        manifest.append((ts, url))
                        added += 1
                print(f"   → {added} unique snapshots added (batch total: {len(batch)})")
        except Exception as e:
            print(f"   [!] CDX query failed for {pattern}: {e}")

        time.sleep(0.8)   # polite CDX inter-query delay

    # Sort chronologically (oldest-first for progressive backfill)
    manifest.sort(key=lambda x: x[0])
    print(f"\n[*] Total manifested snapshots: {len(manifest)}")
    return manifest


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 — DOM Extraction
# ─────────────────────────────────────────────────────────────────────────────
def extract_era1_article(soup: BeautifulSoup, ts: str, archive_url: str, original_url: str) -> Optional[Dict]:
    """
    Era 1 (1997-2009): ADN used flat HTML tables and <font> tags.
    We look for the largest contiguous text block as the article body.
    """
    # Try to find headline in <h1> or first large <b> tag
    headline = None
    for tag in soup.find_all(["h1", "h2", "b"]):
        t = tag.get_text(strip=True)
        if 20 < len(t) < 200:
            headline = t
            break

    # Collect body text from <td> or <div> blocks with substantial text
    blocks = []
    for tag in soup.find_all(["td", "div", "p"]):
        t = tag.get_text(separator=" ", strip=True)
        if len(t) > MIN_ARTICLE_BYTES:
            blocks.append(t)

    if not blocks:
        return None

    # Use the longest block as body
    body = max(blocks, key=len)
    if len(body) < MIN_ARTICLE_BYTES:
        return None

    if not headline:
        # Use the first 120 chars of the body as synthetic title
        headline = body[:120].strip() + "…"

    return _build_record(
        headline=headline,
        body=body,
        published_ts=ts_from_wayback(ts),
        original_url=original_url,
        archive_url=archive_url,
    )


def extract_era2_article(soup: BeautifulSoup, ts: str, archive_url: str, original_url: str) -> Optional[Dict]:
    """
    Era 2 (2005-2019): ADN used WordPress / Saxotech CMS with meta tags.
    og:title and og:description are reliable; article body in <article> or .article-body.
    """
    def meta(name: str) -> str:
        m = soup.find("meta", property=name) or soup.find("meta", attrs={"name": name})
        return m["content"].strip() if m and m.get("content") else ""

    headline = meta("og:title") or meta("title")
    description = meta("og:description") or meta("description")

    body = ""
    for sel in ["article", '[class*="article-body"]', '[class*="story-body"]',
                '[class*="entry-content"]', "main"]:
        el = soup.select_one(sel)
        if el:
            body = el.get_text(separator=" ", strip=True)
            break

    if not body:
        # Fall through to Era 1 heuristic
        return extract_era1_article(soup, ts, archive_url, original_url)

    if not headline:
        h1 = soup.find("h1")
        headline = h1.get_text(strip=True) if h1 else body[:120] + "…"

    snippet = description if description else (body[:800] + "…" if len(body) > 800 else body)

    return _build_record(
        headline=headline,
        body=snippet,
        published_ts=ts_from_wayback(ts),
        original_url=original_url,
        archive_url=archive_url,
    )


def extract_era3_article(soup: BeautifulSoup, ts: str, archive_url: str, original_url: str) -> Optional[Dict]:
    """
    Era 3 (2020-today): ADN uses Arc Publishing / Fusion CMS.
    JSON-LD structured data available on most pages.
    """
    # Try JSON-LD first
    for script_tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script_tag.string or "")
            if isinstance(data, list):
                data = data[0]
            atype = data.get("@type", "")
            if atype in ("NewsArticle", "Article", "WebPage"):
                headline  = data.get("headline",    "")
                desc      = data.get("description", "")
                published = data.get("datePublished", ts_from_wayback(ts))

                # Normalise timestamp
                try:
                    published = datetime.fromisoformat(
                        published.replace("Z", "+00:00")
                    ).isoformat()
                except Exception:
                    published = ts_from_wayback(ts)

                if headline and len(headline) > 10:
                    body = desc or headline
                    return _build_record(
                        headline=headline,
                        body=body,
                        published_ts=published,
                        original_url=original_url,
                        archive_url=archive_url,
                    )
        except Exception:
            continue

    # Fall back to Era 2 extractor for generic meta tags
    return extract_era2_article(soup, ts, archive_url, original_url)


def _build_record(headline: str, body: str, published_ts: str,
                  original_url: str, archive_url: str) -> Dict:
    """Assemble a normalised intel record matching the alaskaintel schema."""
    snippet = re.sub(r"\s+", " ", body).strip()
    if len(snippet) > 800:
        snippet = snippet[:800] + "…"

    region   = infer_region(f"{headline} {snippet}")
    category = infer_category_from_url(original_url)
    doc_hash = make_hash(headline, original_url)

    # Pull year from published_ts for the sourceAttribution label
    year_label = published_ts[:4] if published_ts else "Archive"

    return {
        "hash":              doc_hash,
        "id":                f"ADN-{doc_hash[:8]}",
        "source":            "Anchorage Daily News",
        "category":          category,
        "title":             headline.strip(),
        "link":              original_url,
        "sourceUrl":         "https://adn.com",
        "articleUrl":        original_url,
        "archiveUrl":        archive_url,
        "lat":               None,
        "lng":               None,
        "favicon":           "https://www.adn.com/favicon.ico",
        "location":          region,
        "summary":           snippet,
        "dataTag":           f"[Region: {region}] [Category: {category}]",
        "sourceAttribution": f"Source: ADN Historical Archive ({year_label})",
        "section":           category,
        "sourceLean":        "center",
        "topic":             category,
        "timestamp":         published_ts,
        "scraped_at":        datetime.now(timezone.utc).isoformat(),
    }


def parse_snapshot(ts: str, original_url: str, existing_hashes: Set[str]) -> Optional[Dict]:
    """Fetch a Wayback snapshot and route it through the correct era extractor."""
    archive_url = f"http://web.archive.org/web/{ts}id_/{original_url}"
    year = int(ts[:4])

    try:
        resp = requests.get(
            archive_url,
            timeout=25,
            headers={"User-Agent": CHROME_UA},
        )
        if resp.status_code != 200 or len(resp.text) < 300:
            return None
    except Exception as e:
        print(f"     [!] Fetch failed: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Route by era
    if year < 2010:
        record = extract_era1_article(soup, ts, archive_url, original_url)
    elif year < 2020:
        record = extract_era2_article(soup, ts, archive_url, original_url)
    else:
        record = extract_era3_article(soup, ts, archive_url, original_url)

    if not record:
        return None

    h = record["hash"]
    if h in existing_hashes:
        return None   # dedup

    existing_hashes.add(h)
    return record


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Wayback Machine ADN Historical Backfill (1997 – present)"
    )
    parser.add_argument("--from", dest="year_from", type=int, default=1997,
                        help="Start year (default: 1997)")
    parser.add_argument("--to",   dest="year_to",   type=int,
                        default=datetime.now().year,
                        help="End year (default: current year)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap CDX results per pattern (useful for testing)")
    parser.add_argument("--checkpoint-every", type=int, default=20,
                        help="Save to disk every N new records (default: 20)")
    args = parser.parse_args()

    print("=" * 64)
    print("ADN Wayback Machine Historical Archive Extractor")
    print(f"Coverage: {args.year_from} → {args.year_to}")
    print("=" * 64)

    # Load existing stores
    archive_db = load_json(ADN_ARCHIVE)
    intel_db   = load_json(INTEL_FILE)

    existing_hashes: Set[str] = set()
    for item in archive_db:
        if "hash" in item:
            existing_hashes.add(item["hash"])
    for item in intel_db:
        if "hash" in item:
            existing_hashes.add(item["hash"])

    print(f"[*] Loaded {len(archive_db)} existing ADN archive records.")
    print(f"[*] Intel database: {len(intel_db)} total records.")
    print(f"[*] Dedupe set size: {len(existing_hashes)} hashes.")

    # Phase 1 — build manifest
    manifest = build_cdx_manifest(args.year_from, args.year_to, args.limit)
    if not manifest:
        print("[!] No snapshots found in CDX — exiting.")
        sys.exit(0)

    # Phase 2 — extract signals
    print("\n" + "=" * 64)
    print("Phase 2 — DOM Extraction")
    print("=" * 64)

    total_new   = 0
    pending     = []
    total_snaps = len(manifest)

    try:
        for idx, (ts, original_url) in enumerate(manifest, start=1):
            year  = int(ts[:4])
            month = ts[4:6]
            day   = ts[6:8]
            print(f"\n[{idx}/{total_snaps}] {year}-{month}-{day} → {original_url[:80]}")

            record = parse_snapshot(ts, original_url, existing_hashes)

            if record:
                pending.append(record)
                total_new += 1
                print(f"   [+] Extracted: {record['title'][:70]}")
            else:
                print("   [-] Skipped (empty, duplicate, or parse failure)")

            # Checkpoint every N records
            if len(pending) >= args.checkpoint_every:
                checkpoint(archive_db, intel_db, pending)
                pending = []

            time.sleep(CRAWL_DELAY)

    except KeyboardInterrupt:
        print("\n\n[!] Interrupted by operator — saving progress…")

    # Final flush
    if pending:
        checkpoint(archive_db, intel_db, pending)

    print("\n" + "=" * 64)
    print("✓ ADN ARCHIVE BACKFILL COMPLETE / HALTED")
    print(f"✓ New ADN records extracted : {total_new}")
    print(f"✓ ADN archive total         : {len(archive_db)}")
    print(f"✓ Intel database total      : {len(intel_db)}")
    print("=" * 64)


if __name__ == "__main__":
    main()
