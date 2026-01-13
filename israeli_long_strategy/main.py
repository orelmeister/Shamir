import logging
import sys
from pathlib import Path
import json
import os

# Add current directory to path
sys.path.append(str(Path(__file__).parent))

from data_loader import IsraeliDataLoader
from gov_data_loader import GovDataLoader
from analyzer import SystemicRiskAnalyzer
from reporter import RiskReporter
from html_reporter import HTMLReporter
from translator import RiskTranslator

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(str(Path(__file__).parent / "systemic_risk.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    logger.info("🚀 Starting Israeli Long Opportunity Strategy (Stocks + Kosher ETFs)")
    
    # 1. Load Data
    logger.info("--- Phase 1: Data Ingestion ---")
    # Use the long-universe by default (kosher ETFs + Israeli equities).
    loader = IsraeliDataLoader(universe_path="universe_long.json")
    ecosystem_data = loader.fetch_data()
    
    # Fetch Government Data (Macro Indicators)
    logger.info("--- Phase 1.5: Government Data Ingestion ---")
    gov_loader = GovDataLoader()
    gov_data = gov_loader.fetch_macro_indicators()
    logger.info(f"📊 Government Data Fetched: {list(gov_data.keys())}")
    
    if not ecosystem_data:
        logger.error("❌ No data fetched. Aborting.")
        return

    # 2. Analyze Risks (AI Debate)
    logger.info("--- Phase 2: AI Opportunity Analysis ---")
    analyzer = SystemicRiskAnalyzer()
    analysis_results = analyzer.analyze_ecosystem(ecosystem_data, gov_data=gov_data)
    
    # 3. Optional: Translate to Professional Hebrew
    # Translation is opt-in because LLM calls can be slow; enable via:
    #   ISRAELI_LONG_ENABLE_TRANSLATION=1
    logger.info("--- Phase 3: Optional Translation (Gemini) ---")
    translator = RiskTranslator()
    analysis_results = translator.translate_analysis(analysis_results)
    
    # Save raw results (including translations)
    results_path = os.path.join(Path(__file__).parent, "analysis_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(analysis_results, f, indent=2, ensure_ascii=False)
    logger.info(f"💾 Saved analysis results to {results_path}")
    
    # 4. Generate Reports
    logger.info("--- Phase 4: Report Generation ---")
    
    # HTML Reports (Best for Hebrew)
    html_reporter = HTMLReporter(output_dir=str(Path(__file__).parent))
    html_reporter.generate_report(analysis_results, language='en')
    html_reporter.generate_report(analysis_results, language='he')
    
    # PDF Report (Legacy/Backup)
    report_path = os.path.join(Path(__file__).parent, "Israeli_Long_Opportunity_Report.pdf")
    reporter = RiskReporter(output_path=report_path)
    reporter.generate_report(analysis_results)
    
    logger.info(f"✅ Process Complete. Check HTML reports in {Path(__file__).parent}")

if __name__ == "__main__":
    main()
