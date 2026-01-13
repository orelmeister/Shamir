"""Quick sanity check for Playwright + TASE WAF.

Purpose:
  - Validate Playwright is importable
  - Validate the Chromium binary is installed and can launch
  - Try a best-effort POST to the TASE API from within a browser context

Usage examples:
    python israeli_long_strategy/tmp_playwright_smoke_tase.py --headless
    python israeli_long_strategy/tmp_playwright_smoke_tase.py --headed

Notes:
  - If you get an error about missing browser binaries, run:
      python -m playwright install chromium
"""

from __future__ import annotations

import argparse
import json


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--headless", action="store_true", help="Run headless (default is headed)")
    args = p.parse_args()

    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as e:
        print("FAIL: Could not import Playwright:")
        print(str(e))
        return 2

    api_url = "https://api.tase.co.il/api/security/securitiesinfo"
    payload = {"lang": 1, "pageNum": 1, "pageSize": 5}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        # Prime cookies.
        try:
            page.goto("https://market.tase.co.il/", wait_until="domcontentloaded", timeout=60_000)
            try:
                page.wait_for_load_state("networkidle", timeout=60_000)
            except Exception:
                pass
            page.wait_for_timeout(1500)
        except Exception as e:
            print(f"WARN: market.tase.co.il navigation failed: {e}")

        result = page.evaluate(
            """
            async ({ url, payload }) => {
              const resp = await fetch(url, {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json;charset=UTF-8',
                  'Accept': 'application/json, text/plain, */*'
                },
                credentials: 'include',
                body: JSON.stringify(payload)
              });

              const contentType = resp.headers.get('content-type') || '';
              const text = await resp.text();
              return { status: resp.status, contentType, text };
            }
            """,
            {"url": api_url, "payload": payload},
        )

        try:
            browser.close()
        except Exception:
            pass

    status = int(result.get("status") or 0)
    ctype = result.get("contentType") or ""
    text = result.get("text") or ""

    print(f"HTTP {status} | content-type={ctype}")
    if "application/json" in ctype.lower():
        try:
            obj = json.loads(text)
            # Print only high-level shape to avoid dumping huge payloads.
            if isinstance(obj, dict):
                print("JSON keys:", sorted(list(obj.keys()))[:50])
            elif isinstance(obj, list):
                print(f"JSON list length: {len(obj)}")
            else:
                print("JSON type:", type(obj))
        except Exception:
            print("WARN: content-type said json but body could not be parsed")

    # Always print a tiny snippet for debugging.
    snippet = text.strip().replace("\n", " ")[:250]
    print("Body snippet:")
    print(snippet)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
