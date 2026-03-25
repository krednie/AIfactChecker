"""Quick smoke test for the full verification pipeline."""
import urllib.request
import urllib.parse
import json

BASE = "http://localhost:8000"

TESTS = [
    "iran bombed israel",
    "COVID vaccines contain 5G microchips",
    "iphone 18 launched in india",
    "PM Modi visited France in 2025",
]

for text in TESTS:
    data = urllib.parse.urlencode({"text": text}).encode()
    req = urllib.request.Request(f"{BASE}/analyze", data=data)
    try:
        res = json.loads(urllib.request.urlopen(req, timeout=45).read().decode())
        print(f"\n=== {text!r} ===")
        print(f"Claims: {res['total_claims']} | Time: {res['processing_time_ms']}ms")
        for x in res["results"]:
            print(f"  [{x['stance']} / {x['confidence']}] {x['claim'][:70]}")
            print(f"    {x['reasoning'][:130]}")
    except Exception as e:
        print(f"\n=== {text!r} === ERROR: {e}")
