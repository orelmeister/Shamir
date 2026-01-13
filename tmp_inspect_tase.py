import re
import requests

URL = "https://market.tase.co.il/en/market_data/securities/data/stocks"

html = requests.get(URL, timeout=60).text
print("len", len(html))
print("script_tags", html.lower().count("<script"))
print("api_hits", len(re.findall("api", html, flags=re.I)))
print("contains_json", "json" in html.lower())

script_srcs = re.findall(r"<script[^>]+src=\"([^\"]+)\"", html, flags=re.I)
print("script_srcs", len(script_srcs))
for s in script_srcs[:30]:
    print("script", s)

# Print any obvious API endpoints / JSON config fragments
for m in re.finditer(r"https?://[^\s\"'<>]+", html):
    u = m.group(0)
    if any(k in u.lower() for k in ["api", "json", "service", "graphql"]):
        print("url", u)

# Look for JS config keys commonly used for paging
for key in ["pageSize", "pagesize", "offset", "skip", "take", "limit", "page", "pager", "datatable"]:
    if key.lower() in html.lower():
        print("has_key", key)

print("sample", html[:800].replace("\n", " "))
