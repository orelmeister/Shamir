import json
from pathlib import Path
from typing import Any, Dict, Optional


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


class KosherClassifier:
    """Heuristic + optional LLM-friendly classifier for "kosher candidate" tagging.

    IMPORTANT: This does NOT certify kashrut. It's a screening helper.

    This implementation is intentionally conservative:
    - Auto-exclude obvious categories (e.g., financials/banks) because many kosher-investing
      frameworks avoid interest-based revenue.
    - Mark borderline cases as "manual_review".

    The user's definition of "kosher" can differ by rabbinic authority; this should be treated as
    configurable policy.
    """

    def __init__(self, rules_path: Optional[str] = None):
        if rules_path is None:
            rules_path = str(Path(__file__).parent / "kosher_rules.json")
        self.rules_path = Path(rules_path)
        self.rules = self._load_rules()
        self.overrides_path = Path(__file__).parent / "kosher_overrides.json"
        self.overrides = self._load_overrides()

    def _load_rules(self) -> Dict[str, Any]:
        try:
            with open(self.rules_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            # Safe fallback
            return {
                "auto_exclude_sectors": [],
                "auto_exclude_industry_keywords": ["gambling", "casino", "adult", "porn", "tobacco"],
                "auto_exclude_business_keywords": ["gambling", "casino", "adult", "porn", "tobacco"],
                "auto_include_asset_type": ["ETF"],
                "manual_review_required": True,
            }

    def _load_overrides(self) -> Dict[str, Any]:
        try:
            if not self.overrides_path.exists():
                return {"symbols": {}}
            with open(self.overrides_path, "r", encoding="utf-8") as f:
                return json.load(f) or {"symbols": {}}
        except Exception:
            return {"symbols": {}}

    def classify(self, *, asset_type: str, profile: Dict[str, Any], business_summary: str = "") -> Dict[str, Any]:
        # Manual overrides take precedence.
        symbol = (profile.get("symbol") or profile.get("Symbol") or "").upper().strip()
        if symbol:
            ov = (self.overrides.get("symbols") or {}).get(symbol)
            if isinstance(ov, dict):
                out = dict(ov)
                out.setdefault("manual_review", True)
                out.setdefault("confidence", 0.9)
                out.setdefault("reasons", ["Manual override."])
                out.setdefault("sector", profile.get("sector") or "")
                out.setdefault("industry", profile.get("industry") or "")
                return out

        sector = profile.get("sector") or profile.get("Sector")
        industry = profile.get("industry") or profile.get("Industry")

        sector_n = (sector or "").strip()
        industry_n = (industry or "").strip()

        reasons = []

        # Auto include ETFs (still manual review recommended)
        if (asset_type or "").upper() in [a.upper() for a in (self.rules.get("auto_include_asset_type") or [])]:
            return {
                "kosher_candidate": True,
                "confidence": 0.55,
                "manual_review": True,
                "reasons": ["Asset is an ETF (screening placeholder; requires fund-level verification)."],
                "sector": sector_n,
                "industry": industry_n,
            }

        # Hard excludes by sector
        if sector_n and sector_n in (self.rules.get("auto_exclude_sectors") or []):
            reasons.append(f"Auto-excluded sector: {sector_n}.")

        # Keyword excludes by industry / business summary
        industry_l = _norm(industry_n)
        summary_l = _norm(business_summary)

        for kw in (self.rules.get("auto_exclude_industry_keywords") or []):
            if _norm(kw) and _norm(kw) in industry_l:
                reasons.append(f"Industry keyword match: '{kw}'.")

        for kw in (self.rules.get("auto_exclude_business_keywords") or []):
            if _norm(kw) and _norm(kw) in summary_l:
                reasons.append(f"Business keyword match: '{kw}'.")

        if reasons:
            return {
                "kosher_candidate": False,
                "confidence": 0.8,
                "manual_review": True,
                "reasons": reasons,
                "sector": sector_n,
                "industry": industry_n,
            }

        # Otherwise: unknown/likely okay but needs review
        return {
            "kosher_candidate": True,
            "confidence": 0.45,
            "manual_review": bool(self.rules.get("manual_review_required", True)),
            "reasons": [
                "No exclusion rules matched (heuristic screen).",
                "Shabbat observance / kosher operations require external evidence; treat as preliminary pending manual review."
            ],
            "sector": sector_n,
            "industry": industry_n,
        }
