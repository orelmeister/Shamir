import argparse
import csv
import io
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests


logger = logging.getLogger("tase_universe")


class TaseApiError(RuntimeError):
    pass


class TaseApiBlockedError(TaseApiError):
    """Raised when the TASE API appears to be blocked (e.g., Incapsula/Imperva)."""


def _is_incapsula_block(status_code: int, body: str) -> bool:
    if status_code in {401, 403, 429} and body:
        b = body.lower()
        return (
            "incapsula" in b
            or "_incapsula_resource" in b
            or "request unsuccessful" in b
            or "imperva" in b
        )
    return False


class TaseApiClient:
    """Thin client for https://api.tase.co.il/api/ endpoints.

    Notes:
      * From some networks, TASE is protected by Incapsula/Imperva and will return HTML/403.
      * In that case, use the Playwright fallback (headless browser) to satisfy the JS challenge.
    """

    API_HOST = "https://api.tase.co.il/api/"

    def __init__(self, *, timeout_s: int = 60):
        self.session = requests.Session()
        self.timeout_s = timeout_s
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://market.tase.co.il",
            "Referer": "https://market.tase.co.il/",
        })

    def post_json(self, path: str, payload: Dict[str, Any]) -> Any:
        url = f"{self.API_HOST}{path.lstrip('/')}"
        r = self.session.post(url, json=payload, timeout=self.timeout_s)
        text = r.text or ""
        if _is_incapsula_block(r.status_code, text):
            raise TaseApiBlockedError(f"TASE API blocked (status={r.status_code}).")
        if r.status_code >= 400:
            raise TaseApiError(f"TASE API HTTP {r.status_code}: {text[:200]}")
        try:
            return r.json()
        except Exception as e:
            raise TaseApiError(f"TASE API did not return JSON: {e}")

    def post_json_via_playwright(self, path: str, payload: Dict[str, Any], *, headless: bool = True) -> Any:
        """Fetch JSON via Playwright.

        This can bypass Incapsula/Imperva in many cases because it runs the JS challenge.

        Requires:
          * playwright installed
          * browser binaries installed (e.g., `playwright install`)
        """
        try:
            from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
        except Exception as e:
            raise TaseApiError(
                "Playwright is required for WAF-bypassing mode but could not be imported. "
                "Install it (e.g., `pip install playwright`) and install a browser (e.g., `python -m playwright install chromium`)."
            ) from e

        api_url = f"{self.API_HOST}{path.lstrip('/')}"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                user_agent=self.session.headers.get("User-Agent"),
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()

            # Try to let the WAF set its cookies.
            try:
                page.goto("https://market.tase.co.il/", wait_until="domcontentloaded", timeout=60_000)
                # Let any JS challenges settle.
                try:
                    page.wait_for_load_state("networkidle", timeout=60_000)
                except Exception:
                    pass
                page.wait_for_timeout(1500)

                page.goto("https://api.tase.co.il/", wait_until="domcontentloaded", timeout=60_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=60_000)
                except Exception:
                    pass
                page.wait_for_timeout(1500)
            except Exception:
                # Even if these fail, the subsequent fetch may still work.
                pass

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
        text = result.get("text") or ""
        if _is_incapsula_block(status, text):
            raise TaseApiBlockedError(f"TASE API blocked even via Playwright (status={status}).")
        if status >= 400:
            raise TaseApiError(f"TASE API HTTP {status} via Playwright: {text[:200]}")

        try:
            return json.loads(text)
        except Exception as e:
            raise TaseApiError(f"TASE API did not return JSON via Playwright: {e} | body={text[:200]}")


@dataclass
class CandidateResource:
    package_title: str
    package_name: str
    resource_id: str
    resource_name: str
    resource_format: str
    resource_url: str
    datastore_active: bool
    match_field: Optional[str]
    match_score: int


class DataGovCkanClient:
    BASE_URL = "https://data.gov.il/api/3/action"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "IsraeliLongStrategy/1.0 (TASE Universe Builder)"
        })

    def package_search(self, q: str, rows: int = 10) -> List[Dict[str, Any]]:
        url = f"{self.BASE_URL}/package_search"
        r = self.session.get(url, params={"q": q, "rows": rows}, timeout=30)
        r.raise_for_status()
        data = r.json()
        if not data.get("success"):
            return []
        return data.get("result", {}).get("results", []) or []

    def datastore_search(self, resource_id: str, limit: int = 1, offset: int = 0) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/datastore_search"
        r = self.session.get(url, params={
            "resource_id": resource_id,
            "limit": limit,
            "offset": offset,
        }, timeout=60)
        r.raise_for_status()
        data = r.json()
        if not data.get("success"):
            return {"records": [], "fields": [], "total": 0}
        return data.get("result") or {"records": [], "fields": [], "total": 0}

    def head_bytes(self, url: str, n: int = 65536) -> bytes:
        """Fetch up to n bytes from a URL (best-effort) to infer CSV headers."""
        r = self.session.get(url, stream=True, timeout=60)
        r.raise_for_status()
        buf = bytearray()
        for chunk in r.iter_content(chunk_size=8192):
            if not chunk:
                break
            buf.extend(chunk)
            if len(buf) >= n:
                break
        return bytes(buf)


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _best_symbol_field(record: Dict[str, Any]) -> Tuple[Optional[str], int]:
    """Try to guess the column that contains the ticker/symbol.

    Returns (field_name, score). Higher score = more confident.
    """
    if not record:
        return None, 0

    keys = list(record.keys())
    scored: List[Tuple[int, str]] = []

    # English-ish
    for k in keys:
        kl = _norm(k)
        score = 0
        if kl in {"symbol", "ticker", "tase_symbol", "security_symbol"}:
            score += 50
        if "symbol" in kl:
            score += 20
        if "ticker" in kl:
            score += 20
        if "sec" in kl and "symbol" in kl:
            score += 10

        # Hebrew-ish
        if "סימול" in k:
            score += 40
        if "סימבול" in k:
            score += 40
        if "קוד" in k and "נייר" in k:
            score += 25
        if "נייר" in k and "ערך" in k:
            score += 15

        if score:
            scored.append((score, k))

    if not scored:
        return None, 0
    scored.sort(reverse=True)
    return scored[0][1], scored[0][0]


def _best_symbol_field_from_header(fields: List[str]) -> Tuple[Optional[str], int]:
    dummy = {f: "" for f in fields}
    return _best_symbol_field(dummy)


def discover_tase_symbol_resource(client: DataGovCkanClient, queries: Iterable[str]) -> List[CandidateResource]:
    candidates: List[CandidateResource] = []

    for q in queries:
        try:
            pkgs = client.package_search(q, rows=15)
        except Exception as e:
            logger.warning("Search failed for query '%s': %s", q, e)
            continue

        for pkg in pkgs:
            title = pkg.get("title") or ""
            name = pkg.get("name") or ""
            for res in (pkg.get("resources") or []):
                res_id = res.get("id")
                res_url = res.get("url") or ""
                res_fmt = (res.get("format") or "").upper()
                datastore_active = bool(res.get("datastore_active") or False)

                # Prefer datastore resources when available
                if res_id and datastore_active:
                    try:
                        sample = client.datastore_search(res_id, limit=1, offset=0)
                        recs = sample.get("records") or []
                        record = recs[0] if recs else {}
                        field, score = _best_symbol_field(record)
                    except Exception:
                        field, score = None, 0

                    if score >= 30:
                        candidates.append(CandidateResource(
                            package_title=title,
                            package_name=name,
                            resource_id=res_id,
                            resource_name=res.get("name") or res.get("description") or "",
                            resource_format=res_fmt,
                            resource_url=res_url,
                            datastore_active=True,
                            match_field=field,
                            match_score=score,
                        ))
                    continue

                # Fallback: CSV resources without datastore
                if not res_url:
                    continue
                is_csvish = (res_fmt == "CSV") or res_url.lower().endswith(".csv")
                if not is_csvish:
                    continue

                try:
                    head = client.head_bytes(res_url, n=65536)
                    text = head.decode("utf-8", errors="ignore")
                    # Try to parse the first row as header
                    reader = csv.reader(io.StringIO(text))
                    header = next(reader, [])
                    field, score = _best_symbol_field_from_header(header)
                except Exception:
                    continue

                if score >= 30:
                    candidates.append(CandidateResource(
                        package_title=title,
                        package_name=name,
                        resource_id=res_id or "",
                        resource_name=res.get("name") or res.get("description") or "",
                        resource_format=res_fmt,
                        resource_url=res_url,
                        datastore_active=False,
                        match_field=field,
                        match_score=score,
                    ))

    # Rank by match_score then prefer CSV-ish
    candidates.sort(key=lambda c: (c.match_score, 1 if c.resource_format == "CSV" else 0), reverse=True)
    return candidates


def _looks_like_symbol(v: str) -> bool:
    v = v.strip()
    if not v:
        return False
    # Common Yahoo/TASE patterns are letters/numbers with optional dot.
    return bool(re.fullmatch(r"[A-Z0-9.\-]{1,16}(?:\.TA)?", v, flags=re.IGNORECASE))


def normalize_to_yahoo_ta(symbol: str) -> str:
    s = symbol.strip().upper()
    if s.endswith(".TA"):
        return s
    # If it already contains a dot (e.g., local classification), keep as-is.
    if "." in s:
        return s
    return f"{s}.TA"


def _pick_likely_rows(obj: Any) -> List[Dict[str, Any]]:
    """Try to find the list of security rows inside a response object."""
    if obj is None:
        return []
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if not isinstance(obj, dict):
        return []

    # Common keys
    for k in ("Items", "items", "Securities", "securities", "Data", "data", "Rows", "rows"):
        v = obj.get(k)
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return v

    # Heuristic: pick the largest list-of-dicts.
    best: List[Dict[str, Any]] = []
    for v in obj.values():
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            if len(v) > len(best):
                best = v
    return best


def _extract_symbol_from_row(row: Dict[str, Any]) -> Optional[str]:
    preferred_keys = (
        "Symbol",
        "symbol",
        "SecSymbol",
        "SecuritySymbol",
        "securitySymbol",
        "Ticker",
        "ticker",
        "symbolName",
        "SymbolName",
    )

    for k in preferred_keys:
        v = row.get(k)
        if v:
            s = str(v).strip()
            if _looks_like_symbol(s):
                return normalize_to_yahoo_ta(s)

    # Heuristic fallback: any key that looks like it may hold a symbol/ticker.
    for k, v in row.items():
        if v is None:
            continue
        kl = _norm(str(k))
        if ("symbol" in kl) or ("ticker" in kl) or ("סימול" in str(k)) or ("סימבול" in str(k)):
            s = str(v).strip()
            if _looks_like_symbol(s):
                return normalize_to_yahoo_ta(s)
    return None


def _row_is_stock_or_etf(row: Dict[str, Any]) -> bool:
    """Best-effort filter to keep only instruments that Yahoo Finance is likely to support.

    The TASE APIs can return many instrument types (bonds, options, etc.).
    For market scanning via yfinance, we primarily want equities and ETFs.
    """

    t = str(row.get("Type") or row.get("type") or "").strip().lower()
    sub = str(row.get("SecuritySubType") or row.get("securitySubType") or "").strip().lower()

    # Exclude obvious non-equity instruments.
    if "bond" in t or "bond" in sub:
        return False
    if "option" in t or "option" in sub:
        return False
    if "future" in t or "future" in sub:
        return False

    # Include likely equities/ETFs.
    if t in {"shares", "share", "etf", "etfs"}:
        return True
    if "share" in t or "etf" in t:
        return True
    if "etf" in sub:
        return True

    # Conservative default: skip unknown types.
    return False


def build_universe_from_tase_api(
    *,
    lang: int = 1,
    use_playwright: str = "auto",
    playwright_headless: bool = True,
    include_raw: bool = False,
    page_size: int = 1000,
    max_pages: int = 200,
) -> Dict[str, Any]:
    """Build a TASE universe from TASE's own API.

    Returns a payload compatible with `israel_market_scanner.py` (contains a `tickers` array).

    Caveat:
      The API may be blocked by Incapsula/Imperva for automated clients; in that case we can
      optionally use Playwright.
    """
    client = TaseApiClient()

    def call(path: str, payload: Dict[str, Any]) -> Any:
        if use_playwright == "always":
            return client.post_json_via_playwright(path, payload, headless=playwright_headless)
        try:
            return client.post_json(path, payload)
        except TaseApiBlockedError:
            if use_playwright in {"auto", "always"}:
                return client.post_json_via_playwright(path, payload, headless=playwright_headless)
            raise

    # First try "fetch all" conventions (some endpoints support pageNum=-1).
    tried_payloads = [
        {"lang": lang, "pageNum": -1},
        {"lang": lang, "pageNum": -1, "pageSize": page_size},
    ]

    endpoints = ["security/securitiesinfo", "security/securitiesmarketdata"]

    last_err: Optional[Exception] = None
    for endpoint in endpoints:
        for pld in tried_payloads:
            try:
                data = call(endpoint, pld)
                rows = _pick_likely_rows(data)
                if not rows:
                    continue

                symbols: List[str] = []
                securities: List[Dict[str, Any]] = []
                for r in rows:
                    if not _row_is_stock_or_etf(r):
                        continue
                    sym = _extract_symbol_from_row(r)
                    if sym:
                        symbols.append(sym)
                        if include_raw:
                            securities.append(r)

                # de-dupe
                seen = set()
                tickers: List[str] = []
                for s in symbols:
                    if s not in seen:
                        seen.add(s)
                        tickers.append(s)

                if tickers:
                    payload = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "source": "tase_api",
                        "api_host": client.API_HOST,
                        "endpoint": endpoint,
                        "request": pld,
                        "tickers": tickers,
                    }
                    if include_raw:
                        payload["securities_raw"] = securities
                    return payload
            except Exception as e:
                last_err = e

    # Fallback: paginate.
    symbols: List[str] = []
    securities: List[Dict[str, Any]] = []
    for endpoint in endpoints:
        symbols.clear()
        securities.clear()
        seen_row_ids: set[str] = set()
        for page_num in range(1, max_pages + 1):
            pld = {"lang": lang, "pageNum": page_num, "pageSize": page_size}
            try:
                data = call(endpoint, pld)
            except Exception as e:
                last_err = e
                break

            rows = _pick_likely_rows(data)
            if not rows:
                break

            new_rows = 0

            for r in rows:
                # Some endpoints enforce a fixed server-side page size; avoid infinite loops
                # by stopping when we stop seeing new unique rows.
                row_id = str(r.get("Id") or r.get("id") or r.get("ISIN_ID") or r.get("isin") or "")
                if row_id:
                    if row_id in seen_row_ids:
                        continue
                    seen_row_ids.add(row_id)
                new_rows += 1

                if not _row_is_stock_or_etf(r):
                    continue
                sym = _extract_symbol_from_row(r)
                if sym:
                    symbols.append(sym)
                    if include_raw:
                        securities.append(r)

            if new_rows == 0:
                break

            time.sleep(0.15)

        # de-dupe
        seen = set()
        tickers = []
        for s in symbols:
            if s not in seen:
                seen.add(s)
                tickers.append(s)

        if tickers:
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "tase_api",
                "api_host": client.API_HOST,
                "endpoint": endpoint,
                "request": {"lang": lang, "pageSize": page_size, "pagination": True},
                "tickers": tickers,
            }
            if include_raw:
                payload["securities_raw"] = securities
            return payload

    if last_err:
        raise last_err
    raise TaseApiError("TASE API returned no usable security rows.")


def extract_symbols_from_resource(
    client: DataGovCkanClient,
    resource_id: str,
    symbol_field: str,
    *,
    limit_per_page: int = 1000,
    max_records: Optional[int] = None,
) -> List[str]:
    out: List[str] = []
    offset = 0

    while True:
        res = client.datastore_search(resource_id, limit=limit_per_page, offset=offset)
        records = res.get("records") or []
        if not records:
            break

        for r in records:
            raw = r.get(symbol_field)
            if raw is None:
                continue
            s = str(raw).strip()
            if not _looks_like_symbol(s):
                continue
            out.append(normalize_to_yahoo_ta(s))

        offset += len(records)
        if max_records and len(out) >= max_records:
            out = out[:max_records]
            break

    # de-dupe while preserving order
    seen = set()
    deduped = []
    for s in out:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped


def extract_symbols_from_csv_url(
    client: DataGovCkanClient,
    url: str,
    symbol_field: str,
    *,
    max_records: Optional[int] = None,
) -> List[str]:
    r = client.session.get(url, timeout=120)
    r.raise_for_status()

    # Some resources are encoded in windows-1255; utf-8-sig also common
    text = r.content.decode("utf-8", errors="ignore")
    if not text.strip():
        text = r.content.decode("cp1255", errors="ignore")

    reader = csv.DictReader(io.StringIO(text))
    out: List[str] = []
    for row in reader:
        raw = row.get(symbol_field)
        if raw is None:
            continue
        s = str(raw).strip()
        if not _looks_like_symbol(s):
            continue
        out.append(normalize_to_yahoo_ta(s))
        if max_records and len(out) >= max_records:
            break

    # de-dupe preserving order
    seen = set()
    deduped = []
    for s in out:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    p = argparse.ArgumentParser(
        description=(
            "Build a TASE ticker universe. Supports: (1) direct TASE API (preferred), "
            "(2) CKAN discovery via data.gov.il (fallback)."
        )
    )
    p.add_argument("--out", default=str(Path(__file__).parent / "tase_tickers.json"))
    p.add_argument("--max", type=int, default=None, help="Optional cap on number of tickers")
    p.add_argument("--print-candidates", action="store_true", help="Print dataset/resource candidates and exit")
    p.add_argument("--debug-search", action="store_true", help="Print top package titles for each query")
    p.add_argument(
        "--source",
        choices=["auto", "tase_api", "ckan"],
        default="auto",
        help="Where to build the universe from. 'auto' tries TASE API first, then CKAN.",
    )
    p.add_argument(
        "--lang",
        choices=["en", "he"],
        default="en",
        help="Language hint for TASE API calls (affects some payloads/labels).",
    )
    p.add_argument(
        "--playwright",
        choices=["auto", "always", "never"],
        default="auto",
        help="Use Playwright for TASE API calls when blocked by Incapsula/Imperva.",
    )
    p.add_argument(
        "--headed",
        action="store_true",
        help="Run Playwright in headed mode (can help with some WAFs that dislike headless browsers).",
    )
    p.add_argument(
        "--include-raw",
        action="store_true",
        help="Include raw security rows in the output JSON (can be very large).",
    )

    args = p.parse_args(argv)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 1) Try TASE API first (preferred)
    lang_int = 1 if args.lang == "en" else 0
    if args.source in {"auto", "tase_api"}:
        try:
            payload = build_universe_from_tase_api(
                lang=lang_int,
                use_playwright=args.playwright,
                playwright_headless=(not args.headed),
                include_raw=args.include_raw,
            )
            if args.max is not None:
                payload["tickers"] = payload.get("tickers", [])[: args.max]
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            logger.info("Wrote %d tickers to %s (source=%s)", len(payload.get("tickers") or []), out_path, payload.get("source"))
            return 0
        except Exception as e:
            if args.source == "tase_api":
                logger.error("TASE API universe build failed: %s", e)
                return 2
            logger.warning("TASE API unavailable, falling back to CKAN: %s", e)

    # 2) CKAN fallback
    client = DataGovCkanClient()

    queries = [
        "בורסה",
        "בורסה תל אביב",
        "ניירות ערך",
        "רשימת ניירות ערך",
        "נייר ערך",
        "מסחר בבורסה",
        "רשימת מניות",
        "TASE",
        "Tel Aviv Stock Exchange",
    ]

    if args.debug_search:
        for q in queries:
            try:
                pkgs = client.package_search(q, rows=10)
                titles = [p.get("title") for p in pkgs[:5]]
                print(f"Query: {q} -> {titles}")
            except Exception as e:
                print(f"Query: {q} -> error: {e}")
        return 0

    candidates = discover_tase_symbol_resource(client, queries)
    if not candidates:
        logger.error("No candidate CKAN resources found for TASE tickers.")
        logger.info("Tip: run with --debug-search to see what datasets match, then we can tune discovery.")
        return 2

    if args.print_candidates:
        for c in candidates[:15]:
            print(f"score={c.match_score} | {c.package_title} | res={c.resource_id} | field={c.match_field} | fmt={c.resource_format}")
        return 0

    best = candidates[0]
    if not best.match_field:
        logger.error("Best candidate did not have a symbol field.")
        return 2

    logger.info("Using dataset: %s", best.package_title)
    logger.info("Resource ID: %s", best.resource_id)
    logger.info("Symbol field: %s (score=%s)", best.match_field, best.match_score)

    if best.datastore_active and best.resource_id:
        symbols = extract_symbols_from_resource(client, best.resource_id, best.match_field, max_records=args.max)
    else:
        if not best.resource_url:
            logger.error("Best candidate has no downloadable URL.")
            return 2
        symbols = extract_symbols_from_csv_url(client, best.resource_url, best.match_field, max_records=args.max)
    if not symbols:
        logger.error("No symbols extracted from CKAN resource.")
        return 2

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "data.gov.il CKAN (auto-discovered)",
        "dataset": {
            "title": best.package_title,
            "name": best.package_name,
            "resource_id": best.resource_id,
            "symbol_field": best.match_field,
            "resource_url": best.resource_url,
            "datastore_active": best.datastore_active,
        },
        "tickers": symbols,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    logger.info("Wrote %d tickers to %s", len(symbols), out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
