#!/usr/bin/env python3
"""
Sitemap-Based RSS Discovery — Deep Crawl Strategy
1. Check robots.txt for Sitemap: directives
2. Parse sitemaps for /blog, /news, /feed, /rss paths
3. Scrape discovered pages for <link rel="alternate" type="application/rss+xml">
4. Validate discovered feeds with feedparser
5. Patch fetch_intel.py with working endpoints
"""

import json, re, os, sys, ssl, urllib.parse, time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from xml.etree import ElementTree as ET

try:
    import feedparser
except ImportError:
    print("ERROR: feedparser not installed. Run: pip3 install feedparser")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: beautifulsoup4 not installed. Run: pip3 install beautifulsoup4")
    sys.exit(1)

REPORT_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'feed_health_report.json')
if not os.path.exists(REPORT_FILE):
    REPORT_FILE = '/Users/kb/Library/Mobile Documents/com~apple~CloudDocs/ANTIGRAVITY_BUILDS/ALASKAINTEL_AG-v101/alaskaintel-data/data/feed_health_report.json'

FETCH_SCRIPT = '/Users/kb/Library/Mobile Documents/com~apple~CloudDocs/ANTIGRAVITY_BUILDS/ALASKAINTEL_AG-v101/alaskaintel-data/scripts/fetch_intel.py'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

TIMEOUT = 12

def fetch_url(url):
    """Fetch URL content, returns (text, content_type) or (None, None)."""
    try:
        req = Request(url, headers=HEADERS)
        resp = urlopen(req, context=CTX, timeout=TIMEOUT)
        ct = resp.headers.get('Content-Type', '')
        body = resp.read().decode('utf-8', errors='ignore')
        return body, ct
    except Exception as e:
        return None, None

def get_sitemaps_from_robots(base_url):
    """Parse robots.txt for Sitemap: directives."""
    robots_url = f"{base_url.rstrip('/')}/robots.txt"
    body, _ = fetch_url(robots_url)
    sitemaps = []
    if body:
        for line in body.splitlines():
            line = line.strip()
            if line.lower().startswith('sitemap:'):
                sm_url = line.split(':', 1)[1].strip()
                if sm_url.startswith('//'):
                    sm_url = 'https:' + sm_url
                sitemaps.append(sm_url)
    return sitemaps

def parse_sitemap(url, depth=0):
    """Parse a sitemap XML, return list of URLs. Handles sitemap indexes recursively."""
    if depth > 2:
        return []
    body, ct = fetch_url(url)
    if not body:
        return []
    
    urls = []
    try:
        # Strip namespace for easier parsing
        body_clean = re.sub(r'\sxmlns="[^"]+"', '', body, count=1)
        root = ET.fromstring(body_clean)
        
        # Sitemap index — recurse into child sitemaps
        for sitemap_el in root.findall('.//sitemap'):
            loc = sitemap_el.findtext('loc')
            if loc:
                urls.extend(parse_sitemap(loc.strip(), depth + 1))
        
        # URL set — collect URLs
        for url_el in root.findall('.//url'):
            loc = url_el.findtext('loc')
            if loc:
                urls.append(loc.strip())
    except ET.ParseError:
        pass
    
    return urls

def find_feed_candidates_from_sitemap(sitemap_urls):
    """Filter sitemap URLs for pages likely to contain RSS links (blog, news, feed pages)."""
    feed_keywords = ['feed', 'rss', 'atom', 'blog', 'news', 'articles', 'press', 'media', 'updates', 'stories', 'posts']
    candidates = []
    for url in sitemap_urls:
        url_lower = url.lower()
        # Direct feed URLs
        if any(url_lower.endswith(ext) for ext in ['.xml', '.rss', '.atom', '/feed', '/rss']):
            candidates.append(('direct_feed', url))
        # Pages likely to have RSS links
        elif any(kw in url_lower for kw in feed_keywords):
            candidates.append(('page', url))
    return candidates

def scrape_page_for_rss(url):
    """Scrape a page's HTML for <link rel="alternate" type="application/rss+xml"> tags."""
    body, ct = fetch_url(url)
    if not body:
        return []
    
    feeds = []
    try:
        soup = BeautifulSoup(body, 'html.parser')
        for link in soup.find_all('link', rel='alternate'):
            link_type = link.get('type', '').lower()
            href = link.get('href', '')
            if href and ('rss' in link_type or 'atom' in link_type or 'xml' in link_type):
                full_url = urllib.parse.urljoin(url, href)
                feeds.append(full_url)
        
        # Also look for <a> tags with feed/rss in href
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href'].lower()
            if 'feed' in href or 'rss' in href or href.endswith('.xml'):
                full_url = urllib.parse.urljoin(url, a_tag['href'])
                if full_url not in feeds:
                    feeds.append(full_url)
    except Exception:
        pass
    
    return feeds

def validate_feed(url):
    """Check if a URL is a valid, working RSS/Atom feed with entries."""
    try:
        parsed = feedparser.parse(url, agent=HEADERS['User-Agent'])
        if not parsed.bozo and len(parsed.entries) > 0:
            return True, len(parsed.entries)
        # Some feeds are "bozo" but still have entries (lenient XML)
        if len(parsed.entries) > 0:
            return True, len(parsed.entries)
        return False, 0
    except Exception:
        return False, 0

def discover_feed_for_domain(base_url, feed_name):
    """Full discovery pipeline for a single domain."""
    print(f"\n{'─'*60}")
    print(f"🔍 {feed_name}")
    print(f"   Base: {base_url}")
    
    # Step 1: Check robots.txt for sitemaps
    sitemaps = get_sitemaps_from_robots(base_url)
    print(f"   📋 Found {len(sitemaps)} sitemap(s) in robots.txt")
    
    # Step 2: Try common sitemap URLs if none found
    if not sitemaps:
        for path in ['/sitemap.xml', '/sitemap_index.xml', '/wp-sitemap.xml', '/sitemap.xml.gz']:
            test_url = f"{base_url.rstrip('/')}{path}"
            body, ct = fetch_url(test_url)
            if body and ('<?xml' in body[:100] or '<urlset' in body[:200] or '<sitemapindex' in body[:200]):
                sitemaps.append(test_url)
                break
    
    if not sitemaps:
        print(f"   ⚠️  No sitemaps found")
    
    # Step 3: Parse sitemaps
    all_sitemap_urls = []
    for sm in sitemaps[:3]:  # limit to 3 sitemaps
        urls = parse_sitemap(sm)
        all_sitemap_urls.extend(urls)
        if len(all_sitemap_urls) > 500:  # don't go crazy
            break
    
    print(f"   📄 Parsed {len(all_sitemap_urls)} URLs from sitemaps")
    
    # Step 4: Find feed candidates from sitemap
    candidates = find_feed_candidates_from_sitemap(all_sitemap_urls)
    print(f"   🎯 Found {len(candidates)} feed/news candidates")
    
    # Step 5: Try direct feed candidates first
    for ctype, url in candidates:
        if ctype == 'direct_feed':
            valid, count = validate_feed(url)
            if valid:
                print(f"   ✅ FOUND VIA SITEMAP: {url} ({count} entries)")
                return url
    
    # Step 6: Try common feed paths based on the base URL 
    common_paths = [
        '/feed', '/feed/', '/rss', '/rss.xml', '/feed.xml', '/atom.xml',
        '/news/feed', '/blog/feed', '/news.rss', '/index.xml',
        '/feed/rss', '/feed/atom', '/?feed=rss2',
        '/news/rss', '/blog/rss', '/updates/feed',
        '/search/?f=rss&t=article&c=news&l=50&s=start_time&sd=desc',  # Town News
    ]
    for path in common_paths:
        test_url = f"{base_url.rstrip('/')}{path}"
        valid, count = validate_feed(test_url)
        if valid:
            print(f"   ✅ FOUND VIA COMMON PATH: {test_url} ({count} entries)")
            return test_url
    
    # Step 7: Scrape the homepage and top candidate pages for RSS <link> tags
    pages_to_scrape = [base_url]
    for ctype, url in candidates[:10]:
        if ctype == 'page':
            pages_to_scrape.append(url)
    
    for page_url in pages_to_scrape[:5]:
        feed_links = scrape_page_for_rss(page_url)
        for feed_url in feed_links[:5]:
            valid, count = validate_feed(feed_url)
            if valid:
                print(f"   ✅ FOUND VIA PAGE SCRAPE ({page_url}): {feed_url} ({count} entries)")
                return feed_url
    
    print(f"   ❌ No working feed found")
    return None


def main():
    # Load the health report
    with open(REPORT_FILE) as f:
        report = json.load(f)
    
    # Get all error+warning feeds
    broken = [f for f in report['feeds'] if f['status'] in ('error', 'warning')]
    
    print(f"🩺 Sitemap-Based Deep Discovery")
    print(f"   Scanning {len(broken)} broken feeds...")
    print(f"   Strategy: robots.txt → sitemaps → page scrape → common paths → validate")
    
    discoveries = {}
    
    for feed in broken:
        name = feed['name']
        old_url = feed['url']
        
        # Extract base domain
        parsed = urllib.parse.urlparse(old_url)
        if not parsed.netloc:
            continue
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        # Skip domains we know are unresolvable
        skip_domains = ['accsp.com', 'inupiatcommunity.com', 'akrdc.org', 'poa.usace.army.mil']
        if parsed.netloc in skip_domains:
            print(f"\n{'─'*60}")
            print(f"⏭️  {name} — skipping known-dead domain")
            continue
        
        result = discover_feed_for_domain(base_url, name)
        if result and result != old_url:
            discoveries[name] = (old_url, result)
        
        time.sleep(0.5)  # be polite
    
    # Summary
    print(f"\n{'='*60}")
    print(f"🎉 DISCOVERY RESULTS")
    print(f"   Found: {len(discoveries)} new endpoints")
    print(f"   Failed: {len(broken) - len(discoveries)}")
    print(f"{'='*60}")
    
    for name, (old, new) in sorted(discoveries.items()):
        print(f"  ✓ {name}")
        print(f"    OLD: {old}")
        print(f"    NEW: {new}")
    
    # Patch fetch_intel.py
    if discoveries and os.path.exists(FETCH_SCRIPT):
        print(f"\n📝 Patching fetch_intel.py with {len(discoveries)} fixes...")
        
        with open(FETCH_SCRIPT, 'r') as f:
            content = f.read()
        
        patched = 0
        for name, (old_url, new_url) in discoveries.items():
            pattern = re.compile(
                rf'(\{{"name":\s*"{re.escape(name)}",\s*"url":\s*")[^"]+(")'
            )
            if pattern.search(content):
                content = pattern.sub(rf'\g<1>{new_url}\g<2>', content)
                patched += 1
        
        if patched > 0:
            with open(FETCH_SCRIPT, 'w') as f:
                f.write(content)
            print(f"✅ Patched {patched} feeds in fetch_intel.py")
    
    # Save discovery results
    results_file = os.path.join(os.path.dirname(REPORT_FILE), 'sitemap_discovery_results.json')
    with open(results_file, 'w') as f:
        json.dump({
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'total_scanned': len(broken),
            'discoveries': {n: {'old': o, 'new': nw} for n, (o, nw) in discoveries.items()},
            'failed_count': len(broken) - len(discoveries),
        }, f, indent=2)
    print(f"\n📊 Results saved to {results_file}")


if __name__ == '__main__':
    main()
