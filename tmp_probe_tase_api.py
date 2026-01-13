import json
import sys
from pprint import pprint

import requests


def probe(path: str, payload: dict):
    url = f"https://api.tase.co.il/api/{path.lstrip('/')}"
    print("\n===", url)
    print("payload:")
    pprint(payload)

    r = requests.post(url, json=payload, timeout=60)
    print("status:", r.status_code)
    print("content-type:", r.headers.get("content-type"))

    # Try JSON pretty-print
    try:
        data = r.json()
        print("json keys:", list(data.keys()) if isinstance(data, dict) else type(data))
        print("json preview:")
        print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
    except Exception:
        print("text preview:")
        print(r.text[:2000])


if __name__ == "__main__":
    tests = [
        ("security/securitiesinfo", {"lang": 1, "pageNum": 1, "pageSize": 10}),
        ("security/securitiesinfo", {"lang": 1, "pageNumber": 1, "pageSize": 10}),
        ("security/securitiesinfo", {"lang": 1, "Page": 1, "PageSize": 10}),
        ("security/securitiesinfo", {"lang": 1}),
        ("security/securitiesmarketdata", {"lang": 1, "pageNum": 1, "pageSize": 10}),
        ("company/tasecompanies", {"lang": 1, "pageNum": 1, "pageSize": 10}),
    ]

    for path, payload in tests:
        try:
            probe(path, payload)
        except Exception as e:
            print("error while probing", path, ":", type(e).__name__, e)
