import os
import json
import logging
import concurrent.futures
from datetime import datetime, timezone
from typing import Dict, List
from dotenv import load_dotenv
from langchain_deepseek import ChatDeepSeek
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from portfolio_builder import build_portfolio

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SystemicRiskAnalyzer:
    def __init__(self):
        disable_llms = os.getenv("ISRAELI_LONG_DISABLE_LLMS", "0").strip() == "1"
        if disable_llms:
            logger.warning("⚠️ ISRAELI_LONG_DISABLE_LLMS=1 set. Running heuristic-only (no LLM calls).")
            self.deepseek = None
            self.gemini = None
        else:
            self.deepseek = self._init_deepseek()
            self.gemini = self._init_gemini()
        
    def _init_deepseek(self):
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            logger.warning("⚠️ DEEPSEEK_API_KEY not found. DeepSeek analysis will be disabled.")
            return None
        return ChatDeepSeek(model="deepseek-reasoner", temperature=0.1)

    def _init_gemini(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("⚠️ GOOGLE_API_KEY not found. Gemini analysis will be disabled.")
            return None
        try:
            # Use Gemini 2.5 Flash as explicitly requested
            return ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.1)
        except:
            logger.warning("⚠️ Gemini 2.5 Flash failed, falling back to standard Pro")
            return ChatGoogleGenerativeAI(model="gemini-pro", temperature=0.1)

    def analyze_ecosystem(self, ecosystem_data: Dict, gov_data: Dict = None) -> Dict:
        """
        Run the full long-opportunity analysis on the ecosystem data.
        """
        logger.info("🧠 Starting Long Opportunity Analysis (DeepSeek vs Gemini)...")
        
        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "bucket_analysis": {},
            "top_long_candidates": [],
            "portfolio": {},
            "gov_data_summary": gov_data
        }
        
        # 1. Analyze each sector in PARALLEL
        tasks = []
        for bucket, companies in ecosystem_data.items():
            logger.info(f"   Queueing Bucket: {bucket.upper()}")
            results["bucket_analysis"][bucket] = []
            for symbol, data in companies.items():
                tasks.append((bucket, data))
        
        # Use ThreadPoolExecutor to run agents in parallel.
        # LLM providers can occasionally stall; we apply an overall timeout and cancel stragglers.
        max_workers = int(os.getenv("ISRAELI_LONG_MAX_WORKERS", "4"))
        analysis_timeout_s = int(os.getenv("ISRAELI_LONG_ANALYSIS_TIMEOUT_S", "180"))

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_bucket = {
                executor.submit(self._analyze_company, data, gov_data): bucket
                for bucket, data in tasks
            }

            done, not_done = concurrent.futures.wait(
                future_to_bucket.keys(),
                timeout=analysis_timeout_s,
                return_when=concurrent.futures.ALL_COMPLETED,
            )

            for future in done:
                bucket = future_to_bucket[future]
                try:
                    analysis = future.result()
                    results["bucket_analysis"][bucket].append(analysis)
                except Exception as e:
                    logger.error(f"Analysis failed for an asset in {bucket}: {e}")

            if not_done:
                logger.warning(
                    f"⏳ Analysis timeout reached ({analysis_timeout_s}s). Canceling {len(not_done)} unfinished tasks."
                )
                for future in not_done:
                    future.cancel()
            
        # 2. Rank Candidates
        all_candidates = []
        for bucket, analyses in results["bucket_analysis"].items():
            all_candidates.extend(analyses)

        def _score(c: Dict) -> float:
            try:
                return float(c.get("long_score", 0) or 0)
            except Exception:
                return 0.0

        # Produce a stable "top list" even when no asset qualifies as BUY.
        # Order preference: BUY candidates first, then WATCH, then AVOID (each bucket sorted by score).
        max_top = int(os.getenv("ISRAELI_LONG_TOP_N", "10"))
        buy = sorted([c for c in all_candidates if c.get("recommendation") == "BUY"], key=_score, reverse=True)
        watch = sorted([c for c in all_candidates if c.get("recommendation") == "WATCH"], key=_score, reverse=True)
        avoid = sorted([c for c in all_candidates if c.get("recommendation") == "AVOID"], key=_score, reverse=True)
        results["top_long_candidates"] = (buy + watch + avoid)[:max_top]

        # 3. Build a simple model portfolio (default $100k)
        results["portfolio"] = build_portfolio(results, total_capital=100_000)
        
        return results

    def _analyze_company(self, data: Dict, gov_data: Dict = None) -> Dict:
        """
        Conduct an AI "debate" for a single asset (stock or ETF).
        """
        symbol = data.get('symbol', data.get('name', 'Unknown'))
        logger.info(f"      Debating {symbol}...")

        asset_name = data.get('name', symbol)
        asset_type = data.get('asset_type', 'STOCK')
        bucket = data.get('bucket', data.get('sector', 'unknown'))
        
        # 1. DeepSeek: Fundamentals / Quality & Valuation
        fundamental_score = 50
        fundamental_reasoning_en = "N/A"
        fundamental_reasoning_he = "N/A"
        
        if self.deepseek:
            try:
                currency = data.get('currency', 'ILS')
                
                gov_context = ""
                if gov_data:
                    gov_context = f"""
                    MACRO CONTEXT (Government Data):
                    - Construction Starts (Trend): {gov_data.get('construction_starts', {}).get('trend', 'Unknown')}
                    - New Dwellings Sold (Trend): {gov_data.get('new_dwellings_sold', {}).get('trend', 'Unknown')}
                    - Construction Input Price Index (Trend): {gov_data.get('cpi_construction', {}).get('trend', 'Unknown')}
                    """

                prompt = f"""
                Analyze {asset_name} ({symbol}) for a LONG thesis.
                Asset type: {asset_type}
                Bucket: {bucket}

                {gov_context}

                Data (Source: Yahoo Finance):
                - Market Cap: {data.get('market_cap')} {currency}
                - Total Debt: {data.get('financial_health', {}).get('total_debt')} {currency}
                - Total Cash: {data.get('financial_health', {}).get('total_cash')} {currency}
                - Debt/Equity: {data.get('metrics', {}).get('debt_to_equity')}
                - Current Ratio: {data.get('metrics', {}).get('current_ratio')}
                - Trailing P/E: {data.get('metrics', {}).get('trailing_pe')}
                - Revenue Growth: {data.get('financial_health', {}).get('revenue_growth')}
                - Momentum (6m): {data.get('momentum_6m_pct')}%
                - Thesis/Rationale: {data.get('thesis')}

                INSTRUCTIONS:
                1. Focus on FUNDAMENTALS and QUALITY for a long investor (balance sheet strength, valuation sanity, resilience).
                2. TONE: Professional, serious, plain English.
                3. CITATIONS: Explicitly reference the data points provided above as your source.
                4. OUTPUT: Provide reasoning in BOTH English and Hebrew.

                Return JSON: {{ "score": 0-100, "reasoning_en": "...", "reasoning_he": "..." }}
                (100 = Excellent long opportunity)
                """
                response = self.deepseek.invoke([HumanMessage(content=prompt)])
                # Simple parsing (robustness would need regex)
                content = response.content
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                parsed = json.loads(content)
                fundamental_score = parsed.get('score', 50)
                fundamental_reasoning_en = parsed.get('reasoning_en', '')
                fundamental_reasoning_he = parsed.get('reasoning_he', '')
            except Exception as e:
                logger.error(f"DeepSeek failed for {symbol}: {e}")
        else:
            fundamental_score, fundamental_reasoning_en = self._heuristic_fundamental_score(data)

        # 2. Gemini: Macro / Regime Fit (tailwinds/headwinds)
        macro_score = 50
        macro_reasoning_en = "N/A"
        macro_reasoning_he = "N/A"
        
        if self.gemini:
            try:
                prompt = f"""
                Evaluate the MACRO backdrop for a LONG position in {asset_name} ({symbol}).

                Use the government macro indicators (construction starts, new dwellings sold, construction input price index) if present.
                Consider Israel-specific factors:
                - War / security risk and labor availability
                - Interest rates and credit conditions
                - Consumer confidence and housing demand (if relevant)

                Thesis/Rationale: {data.get('thesis')}

                INSTRUCTIONS:
                1. Focus on regime fit: do current macro conditions SUPPORT a long position?
                2. TONE: Professional, serious, plain English.
                3. OUTPUT: Provide reasoning in BOTH English and Hebrew.

                Return JSON: {{ "score": 0-100, "reasoning_en": "...", "reasoning_he": "..." }}
                (100 = strong macro tailwind for a long)
                """
                response = self.gemini.invoke([HumanMessage(content=prompt)])
                content = response.content
                # Clean potential markdown code blocks
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                
                # Clean control characters that might break JSON parsing
                content = content.replace('\n', ' ').replace('\r', '').strip()
                
                parsed = json.loads(content)
                macro_score = parsed.get('score', 50)
                macro_reasoning_en = parsed.get('reasoning_en', '')
                macro_reasoning_he = parsed.get('reasoning_he', '')
            except Exception as e:
                logger.error(f"Gemini failed for {symbol}: {e}")
        else:
            macro_score, macro_reasoning_en = self._heuristic_macro_score(gov_data)

        # 3. Consensus
        avg_score = (fundamental_score + macro_score) / 2

        recommendation = "WATCH"
        if avg_score >= 70:
            recommendation = "BUY"
        elif avg_score < 50:
            recommendation = "AVOID"
            
        return {
            "symbol": data.get('symbol', symbol),
            "name": asset_name,
            "bucket": bucket,
            "asset_type": asset_type,
            "long_score": avg_score,
            "recommendation": recommendation,
            "details": {
                "price": data.get('price'),
                "currency": data.get('currency', 'ILS'),
                "momentum_6m_pct": data.get('momentum_6m_pct'),
                "fundamental_score": fundamental_score,
                "fundamental_reasoning_en": fundamental_reasoning_en,
                "fundamental_reasoning_he": fundamental_reasoning_he,
                "macro_score": macro_score,
                "macro_reasoning_en": macro_reasoning_en,
                "macro_reasoning_he": macro_reasoning_he
            }
        }

    def _heuristic_fundamental_score(self, data: Dict) -> tuple[float, str]:
        """Fallback scoring when LLM keys are missing."""
        score = 50.0
        reasons = []

        metrics = data.get('metrics', {}) or {}
        fin = data.get('financial_health', {}) or {}

        d2e = metrics.get('debt_to_equity')
        if isinstance(d2e, (int, float)):
            if d2e < 50:
                score += 10
                reasons.append(f"Low leverage (Debt/Equity={d2e}).")
            elif d2e < 100:
                score += 5
                reasons.append(f"Moderate leverage (Debt/Equity={d2e}).")
            elif d2e > 200:
                score -= 10
                reasons.append(f"High leverage (Debt/Equity={d2e}).")

        current_ratio = metrics.get('current_ratio')
        if isinstance(current_ratio, (int, float)):
            if current_ratio >= 1.5:
                score += 5
                reasons.append(f"Strong liquidity (Current Ratio={current_ratio}).")
            elif current_ratio < 1.0:
                score -= 5
                reasons.append(f"Weak liquidity (Current Ratio={current_ratio}).")

        rev_growth = fin.get('revenue_growth')
        if isinstance(rev_growth, (int, float)):
            if rev_growth > 0:
                score += 5
                reasons.append(f"Positive revenue growth ({rev_growth}).")
            elif rev_growth < 0:
                score -= 5
                reasons.append(f"Negative revenue growth ({rev_growth}).")

        pe = metrics.get('trailing_pe')
        if isinstance(pe, (int, float)):
            if pe <= 20:
                score += 3
                reasons.append(f"Reasonable valuation (P/E={pe}).")
            elif pe >= 40:
                score -= 3
                reasons.append(f"Expensive valuation (P/E={pe}).")

        mom = data.get('momentum_6m_pct')
        if isinstance(mom, (int, float)):
            if mom >= 10:
                score += 5
                reasons.append(f"Positive momentum (6m={mom}%).")
            elif mom < -10:
                score -= 5
                reasons.append(f"Negative momentum (6m={mom}%).")

        score = max(0.0, min(100.0, score))
        if not reasons:
            reasons.append("Insufficient fundamentals data; neutral score.")

        return score, " ".join(reasons)

    def _heuristic_macro_score(self, gov_data: Dict) -> tuple[float, str]:
        if not gov_data:
            return 50.0, "No government macro data available; neutral macro score."
        return 50.0, "Government macro data available; qualitative interpretation recommended."
