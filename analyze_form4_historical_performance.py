"""
Historical Performance Analysis for Form 4 Strategy
====================================================

Analyzes all Form 4 positions from inception to validate hypothesis:
"Politicians > Directors > Officers" in terms of trading signal quality

Uses multi-agent debate (DeepSeek Reasoner + Gemini 3.0 Pro) for insights.
"""

import os
import sys
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import json
import requests
from collections import defaultdict
from dotenv import load_dotenv

# LangChain imports
from langchain_deepseek import ChatDeepSeek
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    GEMINI_AVAILABLE = True
except (ImportError, AttributeError):
    GEMINI_AVAILABLE = False
    print("[WARNING] Gemini unavailable - multi-agent debate disabled")

from langchain_core.messages import HumanMessage, SystemMessage

# PDF generation
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("[WARNING] reportlab not installed - PDF generation disabled")

# Load environment variables
load_dotenv()

# API Keys
FMP_API_KEY = os.getenv("FMP_API_KEY", "Q0MEUK8wi0TxCWR036LRxP8jSRdxZbhg")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Database path
DB_PATH = Path("databases/trading_history.db")

print("\n" + "="*80)
print("FORM 4 HISTORICAL PERFORMANCE ANALYSIS")
print("="*80 + "\n")

class HistoricalPerformanceAnalyzer:
    """Analyze historical Form 4 trading performance with multi-agent debate"""
    
    def __init__(self):
        self.db_path = DB_PATH
        self.output_dir = Path("weekly_bot/form4_reports")
        self.output_dir.mkdir(exist_ok=True, parents=True)
        
        # Initialize LLMs for multi-agent debate
        self.deepseek_llm = None
        self.gemini_llm = None
        self.multi_agent_available = False
        
        self._initialize_llms()
    
    def _initialize_llms(self):
        """Initialize DeepSeek Reasoner + Gemini 3.0 Pro"""
        # DeepSeek Reasoner
        if DEEPSEEK_API_KEY:
            try:
                self.deepseek_llm = ChatDeepSeek(
                    model="deepseek-reasoner",
                    temperature=0.1
                )
                print("[✓] DeepSeek Reasoner initialized")
            except Exception as e:
                print(f"[✗] DeepSeek initialization failed: {e}")
        
        # Gemini 2.0 Flash Exp (latest available model)
        if GOOGLE_API_KEY and GEMINI_AVAILABLE:
            try:
                self.gemini_llm = ChatGoogleGenerativeAI(
                    model="gemini-2.0-flash-exp",
                    temperature=0.1
                )
                print("[✓] Gemini 2.0 Flash Exp initialized")
            except Exception as e:
                print(f"[✗] Gemini 2.0 Flash Exp initialization failed: {e}")
                # Fallback to Gemini 2.0 Flash Thinking if 3.0 Pro unavailable
                try:
                    self.gemini_llm = ChatGoogleGenerativeAI(
                        model="gemini-2.0-flash-thinking-exp",
                        temperature=0.1
                    )
                    print("[✓] Gemini 2.0 Flash Thinking initialized (fallback)")
                except Exception as e2:
                    print(f"[✗] Gemini fallback failed: {e2}")
        
        # Check if multi-agent available
        if self.deepseek_llm and self.gemini_llm:
            self.multi_agent_available = True
            print("[✓] Multi-agent debate ENABLED\n")
        else:
            print("[!] Multi-agent debate DISABLED - missing LLM API keys\n")
    
    def fetch_all_positions(self) -> List[Dict]:
        """Fetch all Form 4 strategy positions from database"""
        print("[STEP 1] Fetching all Form 4 positions from database...")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Query all BUY trades for form4_strategy (or form4_exit_manager)
        cursor.execute("""
            SELECT symbol, action, quantity, price, timestamp, metadata
            FROM trades
            WHERE agent_name IN ('form4_strategy', 'form4_exit_manager')
            AND action = 'BUY'
            ORDER BY timestamp ASC
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        positions = []
        for row in rows:
            symbol, action, quantity, price, timestamp, metadata = row
            
            # Parse timestamp
            try:
                entry_date = datetime.fromisoformat(timestamp)
            except:
                entry_date = datetime.now()
            
            # Parse metadata
            try:
                metadata_dict = json.loads(metadata) if metadata else {}
            except:
                metadata_dict = {}
            
            positions.append({
                'symbol': symbol,
                'quantity': quantity,
                'entry_price': price,
                'entry_date': entry_date,
                'metadata': metadata_dict
            })
        
        print(f"   [✓] Found {len(positions)} BUY transactions\n")
        return positions
    
    def fetch_current_prices(self, positions: List[Dict]) -> List[Dict]:
        """Fetch current prices for all positions"""
        print("[STEP 2] Fetching current prices from FMP...")
        
        symbols = [p['symbol'] for p in positions]
        symbols_str = ",".join(symbols)
        
        url = f"https://financialmodelingprep.com/api/v3/quote/{symbols_str}"
        params = {"apikey": FMP_API_KEY}
        
        try:
            response = requests.get(url, params=params, timeout=30)
            if response.status_code == 200:
                quotes = response.json()
                quote_dict = {q['symbol']: q['price'] for q in quotes}
                
                # Update positions with current prices
                for p in positions:
                    p['current_price'] = quote_dict.get(p['symbol'], p['entry_price'])
                
                print(f"   [✓] Fetched prices for {len(quotes)} stocks\n")
            else:
                print(f"   [✗] API error: {response.status_code}\n")
                # Use entry prices as fallback
                for p in positions:
                    p['current_price'] = p['entry_price']
        except Exception as e:
            print(f"   [✗] Error fetching prices: {e}\n")
            for p in positions:
                p['current_price'] = p['entry_price']
        
        return positions
    
    def calculate_performance_metrics(self, positions: List[Dict]) -> List[Dict]:
        """Calculate ROI, hold period, daily returns, etc."""
        print("[STEP 3] Calculating performance metrics...")
        
        for p in positions:
            # Hold period (handle both timezone-aware and naive datetimes)
            entry_date = p['entry_date']
            if entry_date.tzinfo is not None:
                # entry_date is timezone-aware, make now() timezone-aware too
                now = datetime.now(entry_date.tzinfo)
            else:
                # entry_date is timezone-naive
                now = datetime.now()
            hold_days = (now - entry_date).days
            p['hold_days'] = max(hold_days, 0)
            
            # ROI
            roi = ((p['current_price'] - p['entry_price']) / p['entry_price']) * 100
            p['roi_pct'] = round(roi, 2)
            
            # Daily return rate
            if hold_days > 0:
                p['daily_return_pct'] = round(roi / hold_days, 2)
            else:
                p['daily_return_pct'] = 0.0
            
            # Unrealized P&L
            p['unrealized_pnl'] = round((p['current_price'] - p['entry_price']) * p['quantity'], 2)
            
            # Risk-adjusted return (Sharpe-like approximation)
            # Assume 16% annualized volatility (typical for stocks)
            annual_return = p['daily_return_pct'] * 252
            p['risk_adjusted_return'] = round(annual_return / 16, 2)
        
        # Filter out positions with 0 days held (purchased today)
        analyzable = [p for p in positions if p['hold_days'] >= 1]
        excluded = len(positions) - len(analyzable)
        
        print(f"   [✓] Calculated metrics for {len(analyzable)} positions")
        print(f"   [!] Excluded {excluded} positions (0 days held)\n")
        
        return analyzable
    
    def fetch_insider_types(self, positions: List[Dict]) -> List[Dict]:
        """Re-fetch Form 4 data to map insider types for each position"""
        print("[STEP 4] Fetching insider type breakdown from Form 4 filings...")
        
        for p in positions:
            symbol = p['symbol']
            
            # Fetch Form 4 data for this symbol
            insider_breakdown = self._get_insider_breakdown(symbol)
            p['insider_breakdown'] = insider_breakdown
            
            print(f"   {symbol}: Politicians={insider_breakdown['politician_count']}, "
                  f"Directors={insider_breakdown['director_count']}, "
                  f"Officers={insider_breakdown['officer_count']}")
        
        print()
        return positions
    
    def _get_insider_breakdown(self, symbol: str) -> Dict:
        """Fetch Form 4 signals and categorize insiders"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=100)  # Match strategy lookback
        
        breakdown = {
            'politician_count': 0,
            'director_count': 0,
            'officer_count': 0,
            'owner_count': 0,
            'total_signals': 0
        }
        
        # Fetch from all 4 sources
        sources = {
            'insider': f"https://financialmodelingprep.com/api/v4/insider-trading",
            'senate': f"https://financialmodelingprep.com/stable/senate-latest",
            'house': f"https://financialmodelingprep.com/stable/house-latest",
        }
        
        for source_name, url in sources.items():
            try:
                params = {'apikey': FMP_API_KEY}
                if source_name == 'insider':
                    params['symbol'] = symbol
                
                response = requests.get(url, params=params, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    
                    for txn in data:
                        # Check if transaction is for our symbol
                        if txn.get('symbol') != symbol:
                            continue
                        
                        # Check date range
                        txn_date_str = txn.get('transactionDate', '2000-01-01')
                        try:
                            txn_date = datetime.strptime(txn_date_str, '%Y-%m-%d')
                            if not (start_date <= txn_date <= end_date):
                                continue
                        except:
                            continue
                        
                        # Categorize by insider type
                        if source_name in ['senate', 'house']:
                            breakdown['politician_count'] += 1
                        else:
                            role = txn.get('typeOfOwner', '').lower()
                            if 'director' in role or 'board' in role:
                                breakdown['director_count'] += 1
                            elif '10%' in role or '10 percent' in role:
                                breakdown['owner_count'] += 1
                            elif any(w in role for w in ['officer', 'ceo', 'cfo', 'president']):
                                breakdown['officer_count'] += 1
                        
                        breakdown['total_signals'] += 1
            except Exception as e:
                pass  # Skip errors for individual sources
        
        return breakdown
    
    def group_by_insider_type(self, positions: List[Dict]) -> Dict[str, List[Dict]]:
        """Group positions by dominant insider type"""
        print("[STEP 5] Grouping positions by dominant insider type...")
        
        groups = {
            'politician_dominant': [],
            'director_dominant': [],
            'officer_dominant': [],
            'mixed': []
        }
        
        for p in positions:
            breakdown = p['insider_breakdown']
            
            # Determine dominant type
            if breakdown['politician_count'] > 0:
                groups['politician_dominant'].append(p)
            elif breakdown['director_count'] > breakdown['officer_count']:
                groups['director_dominant'].append(p)
            elif breakdown['officer_count'] > breakdown['director_count']:
                groups['officer_dominant'].append(p)
            else:
                groups['mixed'].append(p)
        
        print(f"   Politicians: {len(groups['politician_dominant'])} positions")
        print(f"   Directors: {len(groups['director_dominant'])} positions")
        print(f"   Officers: {len(groups['officer_dominant'])} positions")
        print(f"   Mixed: {len(groups['mixed'])} positions\n")
        
        return groups
    
    def calculate_group_statistics(self, groups: Dict[str, List[Dict]]) -> Dict:
        """Calculate statistics for each insider type group"""
        print("[STEP 6] Calculating group statistics...")
        
        stats = {}
        
        for group_name, positions in groups.items():
            if not positions:
                stats[group_name] = {
                    'count': 0,
                    'avg_roi': 0.0,
                    'median_roi': 0.0,
                    'win_rate': 0.0,
                    'avg_daily_return': 0.0,
                    'total_pnl': 0.0
                }
                continue
            
            rois = [p['roi_pct'] for p in positions]
            daily_returns = [p['daily_return_pct'] for p in positions]
            pnls = [p['unrealized_pnl'] for p in positions]
            
            # Calculate stats
            stats[group_name] = {
                'count': len(positions),
                'avg_roi': round(sum(rois) / len(rois), 2),
                'median_roi': round(sorted(rois)[len(rois)//2], 2),
                'win_rate': round((sum(1 for r in rois if r > 0) / len(rois)) * 100, 1),
                'avg_daily_return': round(sum(daily_returns) / len(daily_returns), 2),
                'total_pnl': round(sum(pnls), 2),
                'best_position': max(positions, key=lambda x: x['roi_pct']),
                'worst_position': min(positions, key=lambda x: x['roi_pct'])
            }
            
            print(f"\n   {group_name.upper()}:")
            print(f"      Count: {stats[group_name]['count']}")
            print(f"      Avg ROI: {stats[group_name]['avg_roi']}%")
            print(f"      Win Rate: {stats[group_name]['win_rate']}%")
            print(f"      Total P&L: ${stats[group_name]['total_pnl']}")
        
        print()
        return stats
    
    def multi_agent_debate_analysis(self, groups: Dict, stats: Dict) -> Dict:
        """Use DeepSeek + Gemini 3.0 Pro debate for insights"""
        print("[STEP 7] Running multi-agent debate for pattern analysis...")
        
        if not self.multi_agent_available:
            print("   [!] Multi-agent debate unavailable - returning basic analysis\n")
            return {
                'consensus': 'Multi-agent debate disabled - missing API keys',
                'confidence': 0.0,
                'recommendations': []
            }
        
        # Build context for debate
        debate_context = self._build_debate_context(groups, stats)
        
        # System prompt
        system_prompt = """You are an expert quantitative analyst specializing in insider trading signals.

Analyze the historical performance data of a Form 4 insider trading strategy.
Focus on identifying which insider types (politicians, directors, officers) provide the most predictive signals.

Current hypothesis: Politicians > Directors > Officers in signal quality.

Your task:
1. Analyze the performance data for each insider type group
2. Identify statistically significant patterns
3. Consider confounding variables (market conditions, sectors, hold periods)
4. Recommend adjustments to signal quality weights
5. Provide confidence score (0.0-1.0) for your recommendations

Return JSON format:
{
    "key_findings": ["finding 1", "finding 2", ...],
    "hypothesis_validation": "supported/refuted/inconclusive",
    "recommended_weights": {
        "politician": 3.0,
        "director": 2.0,
        "officer": 0.5
    },
    "confidence": 0.0-1.0,
    "caveats": ["caveat 1", "caveat 2", ...]
}"""
        
        user_prompt = f"""Analyze this Form 4 strategy historical performance:

{debate_context}

Questions to address:
1. Does the data support "Politicians > Directors > Officers" hierarchy?
2. Are there other factors (timing, coordination, sectors) that matter more?
3. Should we adjust our signal quality weights?
4. What's the confidence level given the sample size?

Provide your analysis in JSON format."""
        
        # Round 1: Independent analysis
        print("   [DEBATE] Round 1: Independent Analysis")
        
        deepseek_analysis = self._get_llm_response(self.deepseek_llm, system_prompt, user_prompt)
        gemini_analysis = self._get_llm_response(self.gemini_llm, system_prompt, user_prompt)
        
        if not deepseek_analysis or not gemini_analysis:
            print("   [✗] Debate failed - LLM error\n")
            return {
                'consensus': 'Debate failed due to LLM errors',
                'confidence': 0.0,
                'recommendations': []
            }
        
        print(f"      DeepSeek confidence: {deepseek_analysis.get('confidence', 0):.0%}")
        print(f"      Gemini confidence: {gemini_analysis.get('confidence', 0):.0%}")
        
        # Round 2: Mutual critique
        print("   [DEBATE] Round 2: Mutual Critique")
        
        critique_prompt_base = """Review your peer's analysis and provide constructive feedback.

Your peer's analysis:
{peer_analysis}

Your original analysis:
{your_analysis}

Questions:
1. What did your peer identify that you missed?
2. Where do you disagree and why?
3. What's your revised confidence score?

Provide revised JSON analysis."""
        
        # DeepSeek critiques Gemini
        deepseek_critique = self._get_llm_response(
            self.deepseek_llm,
            system_prompt,
            critique_prompt_base.format(
                peer_analysis=json.dumps(gemini_analysis, indent=2),
                your_analysis=json.dumps(deepseek_analysis, indent=2)
            )
        )
        
        # Gemini critiques DeepSeek
        gemini_critique = self._get_llm_response(
            self.gemini_llm,
            system_prompt,
            critique_prompt_base.format(
                peer_analysis=json.dumps(deepseek_analysis, indent=2),
                your_analysis=json.dumps(gemini_analysis, indent=2)
            )
        )
        
        # Build consensus
        print("   [DEBATE] Round 3: Building Consensus")
        
        consensus = {
            'deepseek_initial': deepseek_analysis,
            'gemini_initial': gemini_analysis,
            'deepseek_revised': deepseek_critique,
            'gemini_revised': gemini_critique,
            'consensus_findings': self._extract_consensus(deepseek_critique, gemini_critique),
            'agreement_score': self._calculate_agreement(deepseek_critique, gemini_critique)
        }
        
        print(f"      Agreement score: {consensus['agreement_score']:.0%}\n")
        
        return consensus
    
    def _build_debate_context(self, groups: Dict, stats: Dict) -> str:
        """Build formatted context string for debate"""
        context = "HISTORICAL PERFORMANCE DATA:\n\n"
        
        for group_name, group_stats in stats.items():
            if group_stats['count'] == 0:
                continue
            
            context += f"{group_name.upper()}:\n"
            context += f"  Positions: {group_stats['count']}\n"
            context += f"  Avg ROI: {group_stats['avg_roi']}%\n"
            context += f"  Median ROI: {group_stats['median_roi']}%\n"
            context += f"  Win Rate: {group_stats['win_rate']}%\n"
            context += f"  Avg Daily Return: {group_stats['avg_daily_return']}%\n"
            context += f"  Total P&L: ${group_stats['total_pnl']}\n"
            
            if 'best_position' in group_stats:
                best = group_stats['best_position']
                context += f"  Best: {best['symbol']} (+{best['roi_pct']}%)\n"
                worst = group_stats['worst_position']
                context += f"  Worst: {worst['symbol']} ({worst['roi_pct']}%)\n"
            
            context += "\n"
        
        return context
    
    def _get_llm_response(self, llm, system_prompt: str, user_prompt: str) -> Optional[Dict]:
        """Get JSON response from LLM"""
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            response = llm.invoke(messages)
            
            # Parse JSON from response
            content = response.content
            
            # Try to extract JSON if wrapped in markdown
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()
            
            return json.loads(content)
        except Exception as e:
            print(f"      [✗] LLM error: {e}")
            return None
    
    def _extract_consensus(self, deepseek: Dict, gemini: Dict) -> List[str]:
        """Extract consensus findings from both models"""
        findings = []
        
        # Combine key findings
        if deepseek and 'key_findings' in deepseek:
            findings.extend(deepseek['key_findings'])
        if gemini and 'key_findings' in gemini:
            findings.extend(gemini['key_findings'])
        
        # Deduplicate similar findings (simple approach)
        return list(set(findings))
    
    def _calculate_agreement(self, deepseek: Dict, gemini: Dict) -> float:
        """Calculate agreement score between models"""
        if not deepseek or not gemini:
            return 0.0
        
        # Compare recommended weights
        ds_weights = deepseek.get('recommended_weights', {})
        gem_weights = gemini.get('recommended_weights', {})
        
        if not ds_weights or not gem_weights:
            return 0.5
        
        # Calculate average difference in weights
        diffs = []
        for key in ['politician', 'director', 'officer']:
            if key in ds_weights and key in gem_weights:
                diffs.append(abs(ds_weights[key] - gem_weights[key]))
        
        if not diffs:
            return 0.5
        
        avg_diff = sum(diffs) / len(diffs)
        # Convert to agreement score (0 diff = 1.0 agreement, 3.0 diff = 0.0 agreement)
        agreement = max(0.0, 1.0 - (avg_diff / 3.0))
        
        return agreement
    
    def generate_pdf_report(self, positions: List[Dict], groups: Dict, 
                           stats: Dict, debate_results: Dict):
        """Generate comprehensive PDF report"""
        if not REPORTLAB_AVAILABLE:
            print("[!] PDF generation skipped - reportlab not installed\n")
            return
        
        print("[STEP 8] Generating PDF report...")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_path = self.output_dir / f"performance_analysis_{timestamp}.pdf"
        
        doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
        story = []
        styles = getSampleStyleSheet()
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=30,
            alignment=TA_CENTER
        )
        story.append(Paragraph("Form 4 Strategy - Historical Performance Analysis", title_style))
        story.append(Spacer(1, 0.3*inch))
        
        # Executive Summary
        story.append(Paragraph("<b>Executive Summary</b>", styles['Heading2']))
        
        # Handle timezone-aware datetimes for comparison
        entry_dates = [p['entry_date'] for p in positions]
        # Remove timezone info for comparison
        naive_dates = [d.replace(tzinfo=None) if d.tzinfo else d for d in entry_dates]
        min_date = min(naive_dates)
        
        story.append(Paragraph(
            f"Analysis Date: {datetime.now().strftime('%B %d, %Y')}<br/>"
            f"Total Positions Analyzed: {len(positions)}<br/>"
            f"Date Range: {min_date.strftime('%Y-%m-%d')} to "
            f"{datetime.now().strftime('%Y-%m-%d')}",
            styles['Normal']
        ))
        story.append(Spacer(1, 0.2*inch))
        
        # Performance by Insider Type
        story.append(Paragraph("<b>Performance by Insider Type</b>", styles['Heading2']))
        
        # Build table
        table_data = [['Group', 'Count', 'Avg ROI', 'Win Rate', 'Total P&L']]
        for group_name, group_stats in stats.items():
            if group_stats['count'] > 0:
                table_data.append([
                    group_name.replace('_', ' ').title(),
                    str(group_stats['count']),
                    f"{group_stats['avg_roi']}%",
                    f"{group_stats['win_rate']}%",
                    f"${group_stats['total_pnl']}"
                ])
        
        table = Table(table_data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(table)
        story.append(Spacer(1, 0.3*inch))
        
        # Multi-Agent Debate Results
        if self.multi_agent_available and debate_results:
            story.append(Paragraph("<b>Multi-Agent Debate Analysis</b>", styles['Heading2']))
            
            consensus = debate_results.get('consensus_findings', [])
            if consensus:
                story.append(Paragraph("<b>Key Findings:</b>", styles['Heading3']))
                for finding in consensus[:5]:  # Top 5
                    story.append(Paragraph(f"• {finding}", styles['Normal']))
                story.append(Spacer(1, 0.1*inch))
            
            agreement = debate_results.get('agreement_score', 0)
            story.append(Paragraph(
                f"<b>Model Agreement Score:</b> {agreement:.0%}",
                styles['Normal']
            ))
            story.append(Spacer(1, 0.2*inch))
        
        # Individual Position Details
        story.append(PageBreak())
        story.append(Paragraph("<b>Individual Position Details</b>", styles['Heading2']))
        
        # Sort by ROI descending
        sorted_positions = sorted(positions, key=lambda x: x['roi_pct'], reverse=True)
        
        for p in sorted_positions[:15]:  # Top 15
            story.append(Paragraph(
                f"<b>{p['symbol']}</b> - ROI: {p['roi_pct']:+.1f}% | "
                f"Hold: {p['hold_days']} days | "
                f"P&L: ${p['unrealized_pnl']:+.2f}",
                styles['Normal']
            ))
            
            breakdown = p['insider_breakdown']
            story.append(Paragraph(
                f"Insiders: Politicians={breakdown['politician_count']}, "
                f"Directors={breakdown['director_count']}, "
                f"Officers={breakdown['officer_count']}",
                styles['Normal']
            ))
            story.append(Spacer(1, 0.1*inch))
        
        # Build PDF
        doc.build(story)
        print(f"   [✓] PDF saved: {pdf_path}\n")
    
    def run(self):
        """Execute full analysis pipeline"""
        try:
            # Step 1: Fetch positions
            positions = self.fetch_all_positions()
            
            if not positions:
                print("[!] No positions found in database. Exiting.\n")
                return
            
            # Step 2: Fetch current prices
            positions = self.fetch_current_prices(positions)
            
            # Step 3: Calculate metrics
            positions = self.calculate_performance_metrics(positions)
            
            # Step 4: Fetch insider types
            positions = self.fetch_insider_types(positions)
            
            # Step 5: Group by insider type
            groups = self.group_by_insider_type(positions)
            
            # Step 6: Calculate statistics
            stats = self.calculate_group_statistics(groups)
            
            # Step 7: Multi-agent debate
            debate_results = self.multi_agent_debate_analysis(groups, stats)
            
            # Step 8: Generate PDF
            self.generate_pdf_report(positions, groups, stats, debate_results)
            
            print("="*80)
            print("ANALYSIS COMPLETE")
            print("="*80 + "\n")
            
            # Print summary
            print("SUMMARY:")
            print(f"  Total Positions: {len(positions)}")
            print(f"  Politician-dominant: {len(groups['politician_dominant'])} "
                  f"(Avg ROI: {stats['politician_dominant']['avg_roi']}%)")
            print(f"  Director-dominant: {len(groups['director_dominant'])} "
                  f"(Avg ROI: {stats['director_dominant']['avg_roi']}%)")
            print(f"  Officer-dominant: {len(groups['officer_dominant'])} "
                  f"(Avg ROI: {stats['officer_dominant']['avg_roi']}%)")
            
            if debate_results and 'agreement_score' in debate_results:
                print(f"\n  Model Agreement: {debate_results['agreement_score']:.0%}")
            
            print("\n[✓] Check PDF report for full analysis\n")
            
        except Exception as e:
            print(f"\n[ERROR] Analysis failed: {e}\n")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    analyzer = HistoricalPerformanceAnalyzer()
    analyzer.run()
