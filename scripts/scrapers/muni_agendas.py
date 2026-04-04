import json
import requests
from datetime import datetime

# Mocked extraction for demonstration of the signal expansion
# In production, this would use a PDF parser + Gemini LLM for summarization

def fetch_anchorage_assembly_signals():
    # Target URL identified via research
    agenda_url = "https://meetings.muni.org/AgendaOnline/Documents/DownloadFile/Assembly_Regular_-_March_24%2c_2026_6304_Agenda_3_24_2026_5_00_00_PM.pdf?documentType=1&meetingId=6304"
    
    # Simulating the extraction of "Action Items" from the Agenda PDF
    # Based on typical Anchorage Assembly agenda items
    signals = [
        {
            "id": "muni-anch-20260414-001",
            "title": "Ordinance: Zoning Change for Girdwood Residential Expansion",
            "timestamp": "2026-04-14T17:00:00Z",
            "source": "Anchorage Assembly",
            "topic": "Land Use / Housing",
            "category": "Municipal",
            "articleUrl": agenda_url,
            "sourceUrl": "https://www.muni.org/meetings",
            "summary": "The Assembly is considering a major zoning change to allow for increased density in the Girdwood valley to address housing shortages.",
            "impactScore": 7,
            "region": "Anchorage / Girdwood",
            "predictive_weight": 9,
            "document_ref": "Item 14.A - AO 2026-42",
            "isUpcoming": True
        },
        {
            "id": "muni-anch-20260414-002",
            "title": "Resolution: Emergency Shelter Funding Authorization",
            "timestamp": "2026-04-14T17:05:00Z",
            "source": "Anchorage Assembly",
            "topic": "Public Safety / Social Services",
            "articleUrl": agenda_url,
            "sourceUrl": "https://www.muni.org/meetings",
            "summary": "Approval of $2.4M in additional funding for transitional housing and shelter operations through the summer season.",
            "impactScore": 8,
            "region": "Anchorage",
            "predictive_weight": 10,
            "document_ref": "Item 9.B - AR 2026-88",
            "isUpcoming": True
        }
    ]
    
    return signals

if __name__ == "__main__":
    new_signals = fetch_anchorage_assembly_signals()
    print(json.dumps(new_signals, indent=2))
