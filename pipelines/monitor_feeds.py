#!/usr/bin/env python3
"""
Feed Health Monitor
Tests all RSS feed endpoints and generates a health report with probation tracking
"""

import feedparser
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List
import sys
import os
import ssl
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

# Prevent indefinitely hanging on bad server endpoints
socket.setdefaulttimeout(15)

ssl._create_default_https_context = ssl._create_unverified_context

# Import feed list from main scraper
sys.path.insert(0, '.')
from fetch_intel import FEEDS

# Probation configuration
PROBATION_DAYS = 14
REQUIRED_SUCCESS_COUNT = 10  # Minimum successful fetches during probation
MAX_FAILURE_RATE = 0.3  # Maximum 30% failure rate

PROBATION_FILE = 'data/feed_probation.json'
FEED_STATUS_FILE = 'data/feed_status.json'

# After this many consecutive DNS failures, auto-place feed on hold
DNS_HOLD_THRESHOLD = 3

# Error signature strings that indicate a DNS failure (not a transient error)
DNS_ERROR_SIGNATURES = (
    'Failed to resolve',
    'Name or service not known',
    'No address associated with hostname',
    'NameResolutionError',
    '[Errno -2]',
    '[Errno -5]',
    'nodename nor servname provided',
)


import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def test_feed(feed: Dict) -> Dict:
    """Test a single feed and return health status."""
    start = time.time()
    
    # Use a modern Chrome user-agent to reduce blocks from strict servers
    CHROME_UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )
    
    try:
        from interceptor import fetch_feed_robust
        parsed = fetch_feed_robust(feed['url'])
        latency = round((time.time() - start) * 1000)  # ms
        
        if hasattr(parsed, 'status') and parsed.status >= 400:
            return {
                'name': feed['name'],
                'url': feed['url'],
                'category': feed['category'],
                'status': 'error',
                'error': str(getattr(parsed, 'bozo_exception', f"HTTP {parsed.status}")),
                'items': 0,
                'latency_ms': latency,
            }
            
        # Check for valid feed
        entry_count = len(parsed.entries)
        
        if getattr(parsed, 'bozo', False) and entry_count == 0:
            return {
                'name': feed['name'],
                'url': feed['url'],
                'category': feed['category'],
                'status': 'error',
                'error': str(parsed.bozo_exception) if hasattr(parsed, 'bozo_exception') else 'Parse error',
                'items': 0,
                'latency_ms': latency,
            }
        
        # Check for entries
        if entry_count == 0:
            return {
                'name': feed['name'],
                'url': feed['url'],
                'category': feed['category'],
                'status': 'warning',
                'error': 'No entries found in feed',
                'items': 0,
                'latency_ms': latency,
            }
            
        if getattr(parsed, 'bozo', False):
            return {
                'name': feed['name'],
                'url': feed['url'],
                'category': feed['category'],
                'status': 'warning',
                'error': f'Dirty XML (Bozo: {str(getattr(parsed, "bozo_exception", ""))})',
                'items': entry_count,
                'latency_ms': latency,
                'last_updated': getattr(parsed.feed, 'updated', 'Unknown') if hasattr(parsed, 'feed') else 'Unknown',
            }
        
        return {
            'name': feed['name'],
            'url': feed['url'],
            'category': feed['category'],
            'status': 'ok',
            'items': entry_count,
            'latency_ms': latency,
            'last_updated': getattr(parsed.feed, 'updated', 'Unknown') if hasattr(parsed, 'feed') else 'Unknown',
        }
        
    except Exception as e:
        return {
            'name': feed['name'],
            'url': feed['url'],
            'category': feed['category'],
            'status': 'error',
            'error': str(e),
            'items': 0,
            'latency_ms': 0,
        }


def load_probation_data():
    """Load existing probation tracking data."""
    if not os.path.exists(PROBATION_FILE):
        return {
            'metadata': {
                'last_updated': datetime.now().isoformat(),
                'probation_days': PROBATION_DAYS,
                'required_success_count': REQUIRED_SUCCESS_COUNT,
                'max_failure_rate': MAX_FAILURE_RATE
            },
            'feeds': {}
        }
    
    try:
        with open(PROBATION_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load probation data: {e}")
        return {'metadata': {}, 'feeds': {}}


def update_probation_status(probation_data, feed_name, test_result):
    """Update probation tracking for a feed based on test result."""
    if feed_name not in probation_data['feeds']:
        # New feed - add to probation
        probation_data['feeds'][feed_name] = {
            'added_date': datetime.now().isoformat(),
            'status': 'probation',
            'success_count': 0,
            'failure_count': 0,
            'last_success': None,
            'last_failure': None,
            'consecutive_failures': 0
        }
    
    feed_data = probation_data['feeds'][feed_name]
    now = datetime.now().isoformat()
    
    # Update counts based on test result
    if test_result['status'] == 'ok':
        feed_data['success_count'] += 1
        feed_data['last_success'] = now
        feed_data['consecutive_failures'] = 0
    else:
        feed_data['failure_count'] += 1
        feed_data['last_failure'] = now
        feed_data['consecutive_failures'] += 1
    
    # Calculate metrics
    total_tests = feed_data['success_count'] + feed_data['failure_count']
    failure_rate = feed_data['failure_count'] / total_tests if total_tests > 0 else 0
    
    # Determine status
    if feed_data['status'] == 'probation':
        added_date = datetime.fromisoformat(feed_data['added_date'])
        days_in_probation = (datetime.now() - added_date).days
        
        # Graduate from probation if meets criteria
        if (days_in_probation >= PROBATION_DAYS and 
            feed_data['success_count'] >= REQUIRED_SUCCESS_COUNT and
            failure_rate <= MAX_FAILURE_RATE):
            feed_data['status'] = 'approved'
            feed_data['approved_date'] = now
        
        # Fail probation if consistently broken
        elif feed_data['consecutive_failures'] >= 20:
            feed_data['status'] = 'failing'
    
    elif feed_data['status'] == 'approved':
        # Demote to failing if quality degrades
        if feed_data['consecutive_failures'] >= 30:
            feed_data['status'] = 'failing'
    
    elif feed_data['status'] == 'failing':
        # Allow recovery if feed comes back online
        if feed_data['consecutive_failures'] == 0 and feed_data['success_count'] >= 5:
            feed_data['status'] = 'probation'
    
    return feed_data


def save_probation_data(probation_data):
    """Save probation tracking data."""
    probation_data['metadata']['last_updated'] = datetime.now().isoformat()
    
    os.makedirs('data', exist_ok=True)
    with open(PROBATION_FILE, 'w') as f:
        json.dump(probation_data, f, indent=2)


def is_dns_failure(error_str: str) -> bool:
    """Return True if the error string indicates a DNS resolution failure."""
    return any(sig in error_str for sig in DNS_ERROR_SIGNATURES)


def auto_hold_dns_failures(probation_data: dict, results: list) -> list:
    """
    Scans test results for feeds with consecutive DNS failures >= DNS_HOLD_THRESHOLD.
    Auto-adds them to feed_status.json 'hold' list to stop wasting pipeline time.
    Returns list of feed names that were newly held.
    """
    newly_held = []

    # Load current hold/stale state
    hold_list = set()
    stale_list = set()
    try:
        if os.path.exists(FEED_STATUS_FILE):
            with open(FEED_STATUS_FILE, 'r') as f:
                status = json.load(f)
                hold_list = set(status.get('hold', []))
                stale_list = set(status.get('stale', []))
    except Exception:
        pass

    for result in results:
        feed_name = result.get('name', '')
        error_str = result.get('error', '')

        if feed_name in hold_list:
            continue  # Already held

        if result['status'] == 'error' and is_dns_failure(error_str):
            feed_record = probation_data.get('feeds', {}).get(feed_name, {})
            consec = feed_record.get('consecutive_failures', 0)
            consec_dns = feed_record.get('consecutive_dns_failures', 0) + 1
            probation_data['feeds'].setdefault(feed_name, {})['consecutive_dns_failures'] = consec_dns

            if consec_dns >= DNS_HOLD_THRESHOLD:
                hold_list.add(feed_name)
                newly_held.append(feed_name)
                print(f"  🚫 AUTO-HOLD: {feed_name} — {consec_dns} consecutive DNS failures (domain unreachable)")
        else:
            # Clear DNS streak on any non-DNS result
            if feed_name in probation_data.get('feeds', {}):
                probation_data['feeds'][feed_name]['consecutive_dns_failures'] = 0

    if newly_held:
        os.makedirs('data', exist_ok=True)
        with open(FEED_STATUS_FILE, 'w') as f:
            json.dump({'hold': sorted(hold_list), 'stale': sorted(stale_list)}, f, indent=2)
        print(f"\n📋 feed_status.json updated — {len(hold_list)} feeds on hold ({len(newly_held)} new)")

    return newly_held


def verify_proxy_routes(proxy_base: str = 'https://proxy.alaskaintel.com') -> dict:
    """
    Probes all expected /rss/* routes on the proxy worker.
    Returns a dict of slug -> status ('ok', 'error', 'empty').
    """
    EXPECTED_ROUTES = [
        '/rss/adfg-cf',
        '/rss/adfg-sf',
        '/rss/noaa-fisheries',
        '/rss/ast',
        '/rss/usace',
        '/rss/nifc',
        '/rss/dec-air',
        '/rss/rca-orders',
        '/rss/dot-amhs',
        '/rss/labor',
        '/rss/legislature',
    ]

    UA = 'AlaskaIntel-HealthCheck/1.0'
    results = {}
    print(f"\n🔍 Verifying {len(EXPECTED_ROUTES)} proxy routes on {proxy_base}...")

    for route in EXPECTED_ROUTES:
        url = proxy_base + route
        try:
            r = requests.get(url, headers={'User-Agent': UA}, timeout=10, verify=False)
            ct = r.headers.get('Content-Type', '')
            if r.status_code == 200 and ('xml' in ct or 'rss' in ct or len(r.content) > 200):
                # Quick check: does it look like RSS?
                has_rss = b'<rss' in r.content or b'<feed' in r.content or b'<channel' in r.content
                status = 'ok' if has_rss else 'empty'
                icon = '✅' if has_rss else '⚠️ '
            elif r.status_code == 404:
                status = 'missing'
                icon = '❌'
            else:
                status = f'HTTP {r.status_code}'
                icon = '⚠️ '
        except Exception as e:
            status = f'error: {str(e)[:60]}'
            icon = '❌'

        results[route] = status
        print(f"  {icon} {route:30s} → {status}")

    ok_count = sum(1 for s in results.values() if s == 'ok')
    print(f"\n  Proxy routes: {ok_count}/{len(EXPECTED_ROUTES)} live ✅\n")
    return results


def main():
    """Test all feeds and generate health report."""
    print(f"Testing {len(FEEDS)} RSS feeds...\n")
    
    # Load probation tracking
    probation_data = load_probation_data()
    
    results = []
    ok_count = 0
    warn_count = 0
    error_count = 0
    probation_count = 0
    approved_count = 0
    failing_count = 0
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_feed = {executor.submit(test_feed, feed): (i, feed) for i, feed in enumerate(FEEDS, 1)}
        
        for future in as_completed(future_to_feed):
            i, feed = future_to_feed[future]
            try:
                result = future.result()
            except Exception as e:
                result = {
                    'name': feed['name'],
                    'url': feed['url'],
                    'category': feed['category'],
                    'status': 'error',
                    'error': str(e),
                    'items': 0,
                    'latency_ms': 0
                }

            print(f"[{i}/{len(FEEDS)}] Tested {feed['name']}...", end=' ')
            
            # Update probation status
            feed_status = update_probation_status(probation_data, feed['name'], result)
            result['probation_status'] = feed_status['status']
            
            results.append(result)
            
            # Count by test result
            if result['status'] == 'ok':
                print(f"✅ {result['items']} items ({result['latency_ms']}ms) [{feed_status['status'].upper()}]")
                ok_count += 1
            elif result['status'] == 'warning':
                print(f"⚠️  {result['error']} [{feed_status['status'].upper()}]")
                warn_count += 1
            else:
                print(f"❌ {result.get('error', 'Failed')} [{feed_status['status'].upper()}]")
                error_count += 1
            
            # Count by probation status
            if feed_status['status'] == 'probation':
                probation_count += 1
            elif feed_status['status'] == 'approved':
                approved_count += 1
            elif feed_status['status'] == 'failing':
                failing_count += 1
            
            time.sleep(0.01)  # Minimal rate limiting for printing

    # Save probation data
    save_probation_data(probation_data)

    # Auto-hold feeds with chronic DNS failures
    newly_held = auto_hold_dns_failures(probation_data, results)
    
    # Generate summary report
    print(f"\n{'='*70}")
    print(f"FEED HEALTH SUMMARY")
    print(f"{'='*70}")
    print(f"Total Feeds:     {len(FEEDS)}")
    print(f"Healthy:         {ok_count} ({ok_count/len(FEEDS)*100:.1f}%)")
    print(f"Warnings:        {warn_count} ({warn_count/len(FEEDS)*100:.1f}%)")
    print(f"Errors:          {error_count} ({error_count/len(FEEDS)*100:.1f}%)")
    print(f"")
    print(f"PROBATION STATUS:")
    print(f"Approved:        {approved_count} ({approved_count/len(FEEDS)*100:.1f}%)")
    print(f"In Probation:    {probation_count} ({probation_count/len(FEEDS)*100:.1f}%)")
    print(f"Failing:         {failing_count} ({failing_count/len(FEEDS)*100:.1f}%)")
    print(f"{'='*70}\n")
    
    # Show errors first
    if error_count > 0:
        print("❌ FEEDS WITH ERRORS:")
        for r in results:
            if r['status'] == 'error':
                print(f"  - {r['name']}")
                print(f"    URL: {r['url']}")
                print(f"    Error: {r['error']}\n")
    
    if warn_count > 0:
        print("⚠️  FEEDS WITH WARNINGS:")
        for r in results:
            if r['status'] == 'warning':
                print(f"  - {r['name']} - {r['error']}\n")
    
    # Save detailed JSON report
    report = {
        'timestamp': datetime.now().isoformat(),
        'summary': {
            'total': len(FEEDS),
            'healthy': ok_count,
            'warnings': warn_count,
            'errors': error_count,
            'health_score': round(ok_count / len(FEEDS) * 100, 1),
            'approved': approved_count,
            'probation': probation_count,
            'failing': failing_count,
        },
        'feeds': results,
        'probation_config': {
            'probation_days': PROBATION_DAYS,
            'required_success_count': REQUIRED_SUCCESS_COUNT,
            'max_failure_rate': MAX_FAILURE_RATE,
        }
    }
    
    os.makedirs('data', exist_ok=True)
    with open('data/feed_health_report.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"Detailed report saved to: data/feed_health_report.json")
    print(f"Probation tracking saved to: {PROBATION_FILE}")

    # Verify proxy routes (runs quickly, non-blocking)
    verify_proxy_routes()

    # Log warning if too many failures, but do NOT fail the github action
    if error_count > len(FEEDS) * 0.2:  # More than 20% failed
        print("\n⚠️  WARNING: More than 20% of feeds are failing!")
        # We return 0 so the Github Action continues running the rest of the pipeline
        return 0

    return 0


if __name__ == '__main__':
    exit(main())
