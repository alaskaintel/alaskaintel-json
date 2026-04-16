import requests
import json

url = "https://www.namus.gov/api/CaseSets/NamUs/MissingPersons/Search"
payload = {
    "take": 5,
    "skip": 0,
    "predicates": [
        {
            "field": "stateOfLastContact",
            "operator": "==",
            "value": "AK"
        }
    ]
}
headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0"
}

try:
    response = requests.post(url, json=payload, headers=headers)
    print("Search Status:", response.status_code)
    data = response.json()
    print("Total AK Cases:", data.get('totalCount'))
    if data.get('results'):
        first_case = data['results'][0]
        case_id = first_case['id']
        print("\n--- First Search Result ---")
        print(json.dumps(first_case, indent=2))
        
        # Now fetch the specific case details to see photos
        case_url = f"https://www.namus.gov/api/CaseSets/NamUs/MissingPersons/Cases/{case_id}"
        case_resp = requests.get(case_url, headers=headers)
        print("\nCase Details Status:", case_resp.status_code)
        case_data = case_resp.json()
        print("\n--- Specific Case Details (Snippet) ---")
        # Just print keys to see what's available
        print("Keys:", list(case_data.keys()))
        if 'images' in case_data:
            print("Images:", json.dumps(case_data['images'], indent=2))
        if 'sighting' in case_data:
             print("Sighting:", json.dumps(case_data['sighting'], indent=2))
        if 'subjectIdentification' in case_data:
            print("Subject Info:", json.dumps(case_data['subjectIdentification'], indent=2))

except Exception as e:
    print("Error:", e)
