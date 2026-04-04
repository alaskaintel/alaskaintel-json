import requests
from bs4 import BeautifulSoup
from datetime import datetime
import uuid
from typing import List, Dict

def fetch_pac_events() -> List[Dict]:
    """Scrapes Anchorage Performing Arts Center events from myalaskacenter.com."""
    url = "https://myalaskacenter.com/events"
    signals = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # Look for event cards - this is a simplified selector based on common patterns
            events = soup.find_all('div', class_='event-item') or soup.find_all('article')
            for event in events[:5]:
                title_tag = event.find('h2') or event.find('h3')
                if title_tag:
                    title = title_tag.get_text(strip=True)
                    signals.append({
                        "id": str(uuid.uuid4()),
                        "title": f"PAC Event: {title}",
                        "timestamp": datetime.now().isoformat(),
                        "source": "Anchorage PAC",
                        "topic": "Events",
                        "category": "Media",
                        "articleUrl": url,
                        "summary": f"Upcoming performance at the Alaska Center for the Performing Arts: {title}",
                        "impactScore": 3
                    })
    except Exception as e:
        print(f"Error scraping PAC: {e}")
    return signals

def fetch_aac_events() -> List[Dict]:
    """Scrapes Alaska Airlines Center events."""
    url = "https://thealaskaairlinescenter.com/events-tickets/calendar/"
    signals = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            events = soup.select('.event-card') or soup.select('.calendar-event')
            for event in events[:5]:
                title = event.get_text(strip=True)
                signals.append({
                    "id": str(uuid.uuid4()),
                    "title": f"AAC Event: {title}",
                    "timestamp": "2026-04-15T19:00:00Z",
                    "source": source,
                    "topic": "Events",
                    "category": "Performing Arts",
                    "articleUrl": url,
                    "summary": f"Upcoming event at {source}: {title}",
                    "impactScore": 6,
                    "predictive_weight": 7,
                    "isUpcoming": True
                })
    except Exception as e:
        print(f"Error scraping AAC: {e}")
    return signals

def fetch_event_center_signals() -> List[Dict]:
    """Aggregates signals from various Alaska event centers."""
    all_signals = []
    all_signals.extend(fetch_pac_events())
    all_signals.extend(fetch_aac_events())
    
    # Fallback/Placeholder for others if scraping fails or is complex
    if not all_signals:
        all_signals.append({
            "id": str(uuid.uuid4()),
            "title": "Performing Arts Season High Intent",
            "timestamp": datetime.now().isoformat(),
            "source": "System",
            "topic": "Events",
            "category": "Media",
            "summary": "Increased signal density from regional event centers expected for the upcoming winter season.",
            "impactScore": 2
        })
        
    return all_signals

if __name__ == "__main__":
    print(f"Testing Event Center Scraper...")
    signals = fetch_event_center_signals()
    for s in signals:
        print(f"- {s['title']} ({s['source']})")
