#!/usr/bin/env python3
"""
AlaskaIntel Sitemap Generator
===============================
Generates:
  1. public/sitemap.xml          — main SEO sitemap (static routes + archive)
  2. public/sitemap-news.xml     — Google News sitemap (last 48h of articles)
  3. public/sitemaps/feed-<slug>.xml  — per-source Google News sitemaps
  4. public/sitemaps/sitemap-index.xml — index of all sitemaps
"""

import os
import json
import re
from datetime import datetime

SITEMAP_PATH   = "public/sitemaps/sitemap-pages.xml"
NEWS_SITEMAP   = "public/sitemap-news.xml"
FEEDS_DIR      = "public/sitemaps"
INDEX_PATH     = "public/sitemap-index.xml"
INTEL_FILE     = "data/latest_intel.json"
BASE_URL       = "https://alaskaintel.com"

# Google sitemaps namespace
NS_SITEMAP = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
NS_NEWS    = 'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9"'


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def news_url_block(item: dict, today: str) -> list[str]:
    """Return XML lines for one <url> block in a Google News sitemap."""
    link = item.get("link", "")
    if not link.startswith("http"):
        return []
    ts = item.get("timestamp", today)[:10]
    title = (item.get("title", "") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    source = (item.get("source", "Alaska Intel") or "Alaska Intel").replace("&", "&amp;")
    return [
        "  <url>",
        f"    <loc>{link}</loc>",
        "    <news:news>",
        "      <news:publication>",
        f"        <news:name>{source}</news:name>",
        "        <news:language>en</news:language>",
        "      </news:publication>",
        f"      <news:publication_date>{ts}</news:publication_date>",
        f"      <news:title>{title}</news:title>",
        "    </news:news>",
        "  </url>",
    ]


def generate_sitemap():
    print("Generating main SEO Sitemap (2010-2030)...")
    urls = [
        "/", "/all-sources", "/archive", "/privacy", "/terms",
        "/sources", "/accessibility", "/ai-policy", "/api",
        "/disclaimer", "/dmca", "/do-not-sell",
    ]
    for year in range(2010, 2031):
        for month in range(1, 13):
            urls.append(f"/archive/{year}/{month:02d}")

    today = datetime.now().strftime("%Y-%m-%d")
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<urlset {NS_SITEMAP}>']
    for url in urls:
        priority = "1.0" if url == "/" else "0.8" if url.startswith("/archive") else "0.5"
        xml += [
            "  <url>",
            f"    <loc>{BASE_URL}{url}</loc>",
            f"    <lastmod>{today}</lastmod>",
            f"    <priority>{priority}</priority>",
            "  </url>",
        ]
    xml.append("</urlset>")

    with open(SITEMAP_PATH, "w") as f:
        f.write("\n".join(xml))
    print(f"  ✓ sitemaps/sitemap-pages.xml — {len(urls)} endpoints")


def generate_feed_sitemaps(all_items: list[dict]) -> list[str]:
    """
    Build per-source sitemaps. Returns list of R2-relative paths generated.
    """
    os.makedirs(FEEDS_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    by_source: dict[str, list[dict]] = {}

    for item in all_items:
        src = item.get("source", "")
        if src:
            by_source.setdefault(src, []).append(item)

    generated_slugs: list[str] = []

    for source, items in by_source.items():
        slug = slugify(source)
        path = os.path.join(FEEDS_DIR, f"feed-{slug}.xml")
        xml = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<urlset {NS_SITEMAP} {NS_NEWS}>',
        ]
        count = 0
        for item in items[:1000]:
            block = news_url_block(item, today)
            if block:
                xml.extend(block)
                count += 1
        xml.append("</urlset>")
        with open(path, "w") as f:
            f.write("\n".join(xml))
        generated_slugs.append(slug)
        print(f"  ✓ feed-{slug}.xml — {count} articles")

    return generated_slugs


def generate_sitemap_index(feed_slugs: list[str]):
    """Generate sitemap-index.xml listing all sitemaps."""
    os.makedirs(FEEDS_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")

    sitemaps = [
        f"{BASE_URL}/sitemaps/sitemap-pages.xml",
        f"{BASE_URL}/sitemap-news.xml",
    ]
    for slug in feed_slugs:
        sitemaps.append(f"{BASE_URL}/sitemaps/feed-{slug}.xml")

    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url in sitemaps:
        xml += [
            "  <sitemap>",
            f"    <loc>{url}</loc>",
            f"    <lastmod>{today}</lastmod>",
            "  </sitemap>",
        ]
    xml.append("</sitemapindex>")

    with open(INDEX_PATH, "w") as f:
        f.write("\n".join(xml))
    print(f"  ✓ sitemap-index.xml (INDEX) — {len(sitemaps)} sitemaps listed")


def generate_news_sitemap(all_items: list[dict]):
    """Google News sitemap for last 48h (reused from fetch_intel)."""
    today = datetime.now().strftime("%Y-%m-%d")
    recent = all_items[:1000]  # already sorted newest-first

    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<urlset {NS_SITEMAP} {NS_NEWS}>',
    ]
    count = 0
    for item in recent:
        block = news_url_block(item, today)
        if block:
            xml.extend(block)
            count += 1
    xml.append("</urlset>")

    os.makedirs("public", exist_ok=True)
    with open(NEWS_SITEMAP, "w") as f:
        f.write("\n".join(xml))
    print(f"  ✓ sitemap-news.xml — {count} recent articles")


def main():
    print("=" * 60)
    print("AlaskaIntel Sitemap Generator")
    print("=" * 60)

    # Load intel data
    all_items: list[dict] = []
    if os.path.exists(INTEL_FILE):
        try:
            with open(INTEL_FILE) as f:
                all_items = json.load(f)
        except Exception as e:
            print(f"  Warning: could not load {INTEL_FILE}: {e}")

    generate_sitemap()
    generate_news_sitemap(all_items)
    feed_slugs = generate_feed_sitemaps(all_items)
    generate_sitemap_index(feed_slugs)

    print("=" * 60)
    print(f"Done. {len(feed_slugs)} per-feed sitemaps + sitemap.xml (INDEX)")


if __name__ == "__main__":
    main()
