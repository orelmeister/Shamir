import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yfinance as yf

from kosher_classifier import KosherClassifier


@dataclass
class ScanResult:
    symbol: str
    name: str
    price: Optional[float]
    currency: str
    momentum_6m_pct: Optional[float]
    sector: str
    industry: str
    business_summary: str
    kosher: Dict[str, Any]
    news: List[Dict[str, Any]]


def _read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, obj: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def _safe_float(v) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _normalize_tase_price(price: Optional[float], currency: str) -> tuple[Optional[float], str, Optional[float], Optional[str]]:
    if price is None:
        return None, currency, None, None
    c = (currency or "ILS").upper()
    if c == "ILA":
        return price / 100.0, "ILS", price, "ILA"
    return price, c, None, None


def _fetch_one(symbol: str, classifier: KosherClassifier) -> ScanResult:
    t = yf.Ticker(symbol)

    info = t.info or {}
    name = info.get("shortName") or info.get("longName") or symbol
    sector = info.get("sector") or ""
    industry = info.get("industry") or ""
    business_summary = info.get("longBusinessSummary") or ""

    # 6m momentum
    # Use split-adjusted prices to reduce crazy momentum artifacts.
    # yfinance supports auto_adjust which applies splits/dividends adjustments.
    hist = t.history(period="6mo", auto_adjust=True)
    momentum = None
    price = None
    if hist is not None and not hist.empty:
        start = _safe_float(hist["Close"].iloc[0])
        last = _safe_float(hist["Close"].iloc[-1])
        price = last
        if start and last and start != 0:
            raw_mom = ((last - start) / start) * 100.0
            # Guardrail: keep extreme values but avoid letting obvious artifacts dominate.
            if raw_mom > 2000:
                momentum = round(raw_mom, 2)
                # Flag into kosher notes for downstream filtering/LLM review.
                kosher_note = f"Momentum outlier detected (6m={momentum}%). Verify splits/illiquidity/data quality."
            else:
                momentum = round(raw_mom, 2)
                kosher_note = None

    raw_currency = (info.get("currency") or "ILS")
    price_norm, currency_norm, price_raw, currency_raw = _normalize_tase_price(price, raw_currency)

    # Lightweight news (yfinance provides an array of items with title/link/publisher/providerPublishTime)
    news_items = []
    try:
        for item in (t.news or [])[:12]:
            title = item.get("title")
            link = item.get("link")
            if not title and not link:
                continue
            news_items.append({
                "title": title,
                "link": link,
                "publisher": item.get("publisher"),
                "providerPublishTime": item.get("providerPublishTime"),
            })
    except Exception:
        news_items = []

    kosher = classifier.classify(
        asset_type="STOCK",
        profile={"symbol": symbol, "sector": sector, "industry": industry},
        business_summary=business_summary,
    )

    if 'kosher_note' in locals() and kosher_note:
        kosher.setdefault("notes", []).append(kosher_note)

    # Attach raw price metadata for transparency
    if price_raw is not None:
        kosher.setdefault("notes", []).append(f"Price normalized from {price_raw} {currency_raw} to {price_norm} {currency_norm}.")

    return ScanResult(
        symbol=symbol,
        name=name,
        price=price_norm,
        currency=currency_norm,
        momentum_6m_pct=momentum,
        sector=sector,
        industry=industry,
        business_summary=business_summary[:1200],
        kosher=kosher,
        news=news_items,
    )


def run_scan(
    tickers: List[str],
    *,
    max_workers: int = 6,
    max_tickers: Optional[int] = None,
) -> Dict[str, Any]:
    tickers = [t.strip() for t in tickers if t and t.strip()]
    if max_tickers is not None:
        tickers = tickers[: max_tickers]

    classifier = KosherClassifier()

    results: List[Dict[str, Any]] = []
    started = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_fetch_one, sym, classifier): sym for sym in tickers}
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                r = fut.result()
                results.append({
                    "symbol": r.symbol,
                    "name": r.name,
                    "price": r.price,
                    "currency": r.currency,
                    "momentum_6m_pct": r.momentum_6m_pct,
                    "sector": r.sector,
                    "industry": r.industry,
                    "business_summary": r.business_summary,
                    "kosher": r.kosher,
                    "news": r.news,
                })
            except Exception as e:
                results.append({
                    "symbol": sym,
                    "error": str(e),
                })

    # Rank: kosher candidates first, then momentum, then name
    def score(row: Dict[str, Any]) -> tuple:
        kosher = row.get("kosher") or {}
        kosher_flag = bool(kosher.get("kosher_candidate"))
        conf = float(kosher.get("confidence", 0) or 0)
        mom = float(row.get("momentum_6m_pct") or -999)
        return (1 if kosher_flag else 0, conf, mom)

    results_sorted = sorted(results, key=score, reverse=True)

    elapsed_s = round(time.time() - started, 2)

    kosher_candidates = [r for r in results_sorted if (r.get("kosher") or {}).get("kosher_candidate")]

    # Synthetic "ETF" basket: top kosher candidates, capped weights.
    basket = []
    top_n = int(os.getenv("ISRAEL_MARKET_BASKET_N", "12"))
    max_w = float(os.getenv("ISRAEL_MARKET_BASKET_MAX_W", "0.12"))
    picks = [r for r in kosher_candidates if r.get("price")][ : top_n]
    if picks:
        w = min(max_w, 1.0 / max(1, len(picks)))
        for r in picks:
            basket.append({
                "symbol": r.get("symbol"),
                "name": r.get("name"),
                "weight": round(w, 4),
                "reason": (r.get("kosher") or {}).get("reasons", [""])[0],
            })

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "universe_size": len(tickers),
        "elapsed_s": elapsed_s,
        "results": results_sorted,
        "kosher_candidates": kosher_candidates,
        "synthetic_etf_basket": {
            "name": "Israel Kosher Candidate Basket (Synthetic)",
            "top_n": top_n,
            "max_weight": max_w,
            "constituents": basket,
            "disclaimer": "Synthetic research basket only; not a real ETF. Screening is heuristic; validate compliance and investability.",
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Scan a (potentially large) TASE universe and tag kosher candidates.")
    p.add_argument(
        "--tickers-file",
        "--universe",
        dest="tickers_file",
        default=None,
        help="Path to JSON file with a 'tickers' array (alias: --universe)",
    )
    p.add_argument("--max-workers", type=int, default=int(os.getenv("ISRAEL_MARKET_MAX_WORKERS", "6")))
    p.add_argument("--max-tickers", type=int, default=None)
    p.add_argument("--out", default=str(Path(__file__).parent / "market_scan_results.json"))

    args = p.parse_args(argv)

    tickers_file = args.tickers_file
    if not tickers_file:
        # Prefer user-provided list; fall back to sample
        default = Path(__file__).parent / "tase_tickers.json"
        if default.exists():
            tickers_file = str(default)
        else:
            tickers_file = str(Path(__file__).parent / "tase_tickers.sample.json")

    tickers_path = Path(tickers_file)
    if not tickers_path.exists():
        print(f"Tickers file not found: {tickers_path}")
        return 2

    payload = _read_json(tickers_path)
    tickers = payload.get("tickers") or []
    if not tickers:
        print(f"No tickers found in {tickers_path} (expected key: 'tickers')")
        return 2

    scan = run_scan(tickers, max_workers=args.max_workers, max_tickers=args.max_tickers)
    out_path = Path(args.out)
    _write_json(out_path, scan)

    print(f"Wrote scan results: {out_path}")
    print(f"Universe size: {scan['universe_size']} | Elapsed: {scan['elapsed_s']}s")
    print(f"Kosher candidates: {len(scan['kosher_candidates'])}")
    print(f"Synthetic basket constituents: {len(scan['synthetic_etf_basket']['constituents'])}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
