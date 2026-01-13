import math
from typing import Dict, List, Any


def _safe_float(v):
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def build_portfolio(analysis_results: Dict[str, Any], total_capital: float = 100_000) -> Dict[str, Any]:
    """Create a simple, rules-based model portfolio from analysis output.

    Design goals:
    - Prefer ETFs for the "core" allocation when available.
    - Keep position sizing sane (avoid concentration).
    - Return a *suggested* allocation only; execution remains manual.
    """

    candidates: List[Dict[str, Any]] = analysis_results.get("top_long_candidates", []) or []
    # Prefer building a portfolio from actionable ideas. If nothing is BUY yet, WATCH is still useful.
    candidates = [c for c in candidates if (c.get("recommendation") or "").upper() != "AVOID"]

    def _score(c: Dict[str, Any]) -> float:
        try:
            return float(c.get("long_score", 0) or 0)
        except Exception:
            return 0.0

    candidates = sorted(candidates, key=_score, reverse=True)

    # Split into ETFs vs Stocks
    etfs = [c for c in candidates if (c.get("asset_type") or "").upper() == "ETF"]
    stocks = [c for c in candidates if (c.get("asset_type") or "").upper() != "ETF"]

    # Allocation policy
    # If we have ETFs, use them as core.
    target_etf_alloc = 0.70 if etfs else 0.0
    target_stock_alloc = 0.28 if stocks else 0.0
    cash_reserve_pct = 1.0 - (target_etf_alloc + target_stock_alloc)
    cash_reserve_pct = max(0.02, cash_reserve_pct)  # keep at least 2% cash

    # Clamp so weights sum <= 1
    scale = 1.0 / (target_etf_alloc + target_stock_alloc + cash_reserve_pct)
    target_etf_alloc *= scale
    target_stock_alloc *= scale
    cash_reserve_pct *= scale

    # Sizing constraints
    # If the universe currently contains only 1-2 ETFs (common while the kosher ETF list is still being filled),
    # a strict 20% cap leaves the portfolio overly in cash. Loosen ETF caps in that case.
    if len(etfs) <= 1:
        max_etf_weight = 0.60
    elif len(etfs) == 2:
        max_etf_weight = 0.35
    else:
        max_etf_weight = 0.20

    max_stock_weight = 0.12

    positions: List[Dict[str, Any]] = []

    def add_group(group: List[Dict[str, Any]], group_alloc: float, max_weight: float):
        if not group or group_alloc <= 0:
            return

        group = sorted(group, key=_score, reverse=True)

        # Take top-N only to avoid tiny dust positions
        top_n = min(len(group), 6 if max_weight <= 0.12 else 4)
        group = group[:top_n]

        base_weight = group_alloc / top_n
        base_weight = min(base_weight, max_weight)

        # Any leftover (due to caps) stays in cash
        for c in group:
            price = _safe_float(c.get("details", {}).get("price")) or _safe_float(c.get("price"))
            price = price or _safe_float(c.get("last_price"))

            # We may not have a reliable price (TASE via yfinance can be patchy)
            target_weight = base_weight
            target_value = total_capital * target_weight
            shares = None
            if price and price > 0:
                shares = math.floor(target_value / price)
                target_value = shares * price
                target_weight = target_value / total_capital if total_capital else 0

            positions.append({
                "symbol": c.get("symbol"),
                "name": c.get("name"),
                "asset_type": c.get("asset_type"),
                "bucket": c.get("bucket"),
                "long_score": c.get("long_score"),
                "target_weight": round(target_weight, 4),
                "target_value": round(target_value, 2),
                "price": price,
                "shares": shares,
                "rationale_en": c.get("details", {}).get("fundamental_reasoning_en"),
                "rationale_he": c.get("details", {}).get("fundamental_reasoning_he"),
            })

    add_group(etfs, target_etf_alloc, max_etf_weight)
    add_group(stocks, target_stock_alloc, max_stock_weight)

    invested_value = sum(p.get("target_value", 0) for p in positions)
    cash_value = max(0.0, total_capital - invested_value)

    return {
        "total_capital": total_capital,
        "cash_reserve": round(cash_value, 2),
        "cash_reserve_pct": round(cash_value / total_capital, 4) if total_capital else 0,
        "constraints": {
            "max_etf_weight": max_etf_weight,
            "max_stock_weight": max_stock_weight,
            "notes": "If prices are missing, shares are left null and weights reflect targets, not executable quantities. ETF caps may be relaxed when only 1-2 ETFs are available in the candidate list.",
        },
        "positions": positions,
    }
