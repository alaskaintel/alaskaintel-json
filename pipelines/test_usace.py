from curl_cffi import requests

url = "https://www.poa.usace.army.mil/Missions/Regulatory/Public-Notices/"

try:
    r = requests.get(url, impersonate="chrome116", verify=False)
    print("Status:", r.status_code)
    if r.status_code == 200:
        print("Success! Excerpt:")
        print(r.text[:1000])
    else:
        print("Failed:", r.text[:500])
except Exception as e:
    print("Error:", e)
