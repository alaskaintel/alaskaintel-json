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
        resp = requests.get(feed['url'], headers={'User-Agent': CHROME_UA}, timeout=15, verify=False)
        resp.raise_for_status()
        
        parsed = feedparser.parse(resp.content)
        latency = round((time.time() - start) * 1000)  # ms
        
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
    
    # Log warning if too many failures, but do NOT fail the github action
    if error_count > len(FEEDS) * 0.2:  # More than 20% failed
        print("\n⚠️  WARNING: More than 20% of feeds are failing!")
        # We return 0 so the Github Action continues running the rest of the pipeline
        return 0
    
    return 0


if __name__ == '__main__':
    exit(main())
