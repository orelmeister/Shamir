"""Small helper to summarize israel_market_scanner output.

Usage:
  python print_scan_summary.py [market_scan_results.json]

This is intentionally dependency-light and Windows-friendly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _score(row: dict) -> tuple:
    kosher = row.get("kosher") or {}
    kosher_flag = bool(kosher.get("kosher_candidate"))
    conf = float(kosher.get("confidence", 0) or 0)
    mom = float(row.get("momentum_6m_pct") or -999)
    return (1 if kosher_flag else 0, conf, mom)


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else Path(__file__).parent / "market_scan_results.json"
    if not path.exists():
        print(f"Scan results not found: {path}")
        return 2

    obj = json.loads(path.read_text(encoding="utf-8"))
    results = obj.get("results") or []
    results_sorted = sorted(results, key=_score, reverse=True)

    print(f"file: {path}")
    print(f"bytes: {path.stat().st_size}")
    print(f"timestamp: {obj.get('timestamp')}")
    print(f"universe_size: {obj.get('universe_size')}")
    print(f"elapsed_s: {obj.get('elapsed_s')}")
    print(f"kosher_candidates: {len(obj.get('kosher_candidates') or [])}")

    print("\nTop 15 ranked:")
    for r in results_sorted[:15]:
        k = r.get("kosher") or {}
        print(
            f"{r.get('symbol',''):>12} | conf={k.get('confidence')} | mom6m={r.get('momentum_6m_pct')} | sector={r.get('sector','')}"
        )

    basket = (obj.get("synthetic_etf_basket") or {}).get("constituents") or []
    print("\nSynthetic basket:")
    for i, x in enumerate(basket, start=1):
        print(f"{i:02d} {x.get('symbol')} w={x.get('weight')} reason={x.get('reason')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
