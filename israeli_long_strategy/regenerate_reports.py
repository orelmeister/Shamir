import json
import os
import logging
from pathlib import Path
from reporter import RiskReporter
from html_reporter import HTMLReporter
from translator import RiskTranslator

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def regenerate():
    logger.info("🔄 Regenerating Reports from Saved Data...")
    
    json_path = os.path.join(Path(__file__).parent, "analysis_results.json")
    if not os.path.exists(json_path):
        logger.error(f"❌ No saved data found at {json_path}. Run main.py first.")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        analysis_results = json.load(f)
        
    # Optional: Re-translate if requested
    logger.info("--- Phase 3: Professional Translation (Gemini) ---")
    translator = RiskTranslator()
    analysis_results = translator.translate_analysis(analysis_results)
    
    # Save updated results
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(analysis_results, f, indent=2, ensure_ascii=False)

    # Generate HTML Reports
    logger.info("--- Phase 4: Report Generation ---")
    html_reporter = HTMLReporter(output_dir=str(Path(__file__).parent))
    html_reporter.generate_report(analysis_results, language='en')
    html_reporter.generate_report(analysis_results, language='he')
        
    # Generate PDF Report
    report_path = os.path.join(Path(__file__).parent, "Israeli_Long_Opportunity_Report.pdf")
    reporter = RiskReporter(output_path=report_path)
    reporter.generate_report(analysis_results)
    
    logger.info("✅ Reports regenerated successfully.")

if __name__ == "__main__":
    regenerate()
