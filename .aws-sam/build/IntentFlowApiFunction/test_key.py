"""Test the new API key."""
import requests

r = requests.get("https://api.rainforestapi.com/request", params={
    "api_key": "66A90651323A4814AC4439ED4BC2ED1E",
    "type": "search",
    "amazon_domain": "amazon.in",
    "search_term": "puma sneakers"
})

print(f"Status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    results = data.get("search_results", [])
    print(f"Results: {len(results)}")
    for item in results[:3]:
        title = item.get("title", "N/A")[:60]
        price = item.get("price", {}).get("value", "N/A")
        print(f"  - {title} | Rs{price}")
else:
    print(f"Error: {r.text[:300]}")
