# Israeli Long Strategy (Stocks + Kosher ETFs)

An autonomous research + reporting tool that ranks **Israeli long opportunities** and produces a **simple $100,000 model portfolio**.

Primary focus:
- **Kosher ETFs** listed on (or tracking) Tel Aviv market exposures
- **Israeli equities** (quality / value / momentum-aware)

## 📈 Strategy Overview

This system:
1. Loads a universe from `universe_long.json` (buckets like `core_kosher_etfs`, `israeli_quality_stocks`, etc.)
2. Pulls market + fundamentals via Yahoo Finance (yfinance)
3. Pulls macro indicators from Israel's government data portal (data.gov.il)
4. Produces:
	- Ranked long candidates (BUY/WATCH/AVOID)
	- English + Hebrew reasoning (if Gemini key available)
	- A rules-based **$100k model portfolio**

## 🧭 Market-Wide Monitoring Mode (new)

If you want to **monitor the whole Israeli market** (similar spirit to the Form 4 pipeline: scan → news → classify → shortlist), use:

- `israel_market_scanner.py` – scans a ticker universe, pulls:
	- price + 6m momentum
	- sector/industry + business summary
	- recent headlines (via `yfinance.Ticker(...).news`)
	- a **heuristic "kosher candidate" tag** (configurable via `kosher_rules.json`)
	- a **synthetic research basket** ("DIY ETF") of top candidates

### Inputs
- Best: auto-build `tase_tickers.json` using the universe builder:

```powershell
python build_tase_universe.py
```

By default it tries (in order):
1) **TASE public API** (preferred; more complete)
2) **data.gov.il CKAN** discovery (fallback)

If the TASE API returns a `403` HTML page mentioning **Incapsula/Imperva** (WAF protection), try:

```powershell
python build_tase_universe.py --source tase_api --playwright always
```

If your network/browser is still blocked in **headless** mode, try **headed** mode:

```powershell
python build_tase_universe.py --source tase_api --playwright always --headed
```

Playwright requires browser binaries (once per machine):

```powershell
python -m playwright install chromium
```

You can also run a quick smoke test to confirm Playwright can reach the API from your machine:

```powershell
python tmp_playwright_smoke_tase.py --headed
```

- Or start with `tase_tickers.sample.json` and expand manually.

### “Kosher” definition (your policy)
This repo treats "kosher" as a **policy**, not a universal truth:
- Exclude obvious prohibited categories (e.g., gambling/adult content/tobacco) based on available descriptions.
- **Shabbat observance** (e.g., retail open/closed on Shabbat) is not reliably available from market data; the system will generally mark this as **manual review required** unless you provide evidence or an override.

You can add manual decisions in `kosher_overrides.json`.

### Output
- `market_scan_results.json` (default output)

> Note: The kosher classifier is a *screening helper*, not a certification.

## 🚀 Setup Instructions

### 1. Prerequisites
Ensure you have Python 3.10+ installed.

### 2. Environment Setup
Navigate to the project folder and create a virtual environment:

```powershell
cd israeli_long_strategy
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
Install the required packages:

```powershell
pip install -r requirements.txt
pip install --upgrade langchain-core langchain-openai langchain-deepseek
```
*Note: We upgrade langchain packages to fix a known import error.*

### 4. Configure API Keys
Ensure your `.env` file in the repo root contains (optional):

- `DEEPSEEK_API_KEY` (fundamental long-thesis reasoning)
- `GOOGLE_API_KEY` (macro reasoning + Hebrew translation)

### 5. Run the Analysis
Execute the main script:

```powershell
python main.py
```

To run the market scanner:

```powershell
python israel_market_scanner.py --max-tickers 200
```

### 6. Output
The system generates:
- `Israeli_Long_Opportunity_Report.pdf`
- `Israeli_Long_Opportunity_Report.html`
- `Israeli_Long_Opportunity_Report_HE.html`

Plus a JSON artifact: `analysis_results.json` (includes the model portfolio).

## ⚠️ Important Notes
- **Kosher screening:** this project can *track* a `kosher=true` tag in `universe_long.json`, but it does **not** certify compliance. Verify each product/fund with official documents and your rabbinic authority.
- **Data limitations:** Yahoo Finance data for some TASE tickers/ETFs can be incomplete.
- **Manual execution:** this bot provides intelligence only. You are responsible for execution and risk management.
