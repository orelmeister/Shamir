"""
Phase 3.5: Portfolio Review & Approval
Shows current portfolio P&L and proposed trades with LLM explanations.
Waits for manual approval before executing any trades.
"""
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ib_insync import IB, Stock
import ib_insync.util as ib_util
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

# Import shared utilities
from shared_state.state_manager import read_state, write_state
from dotenv import load_dotenv

# PDF generation imports
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("⚠️  reportlab not installed. PDF generation disabled. Install with: pip install reportlab")

# Load environment variables
load_dotenv()

# Configuration
IB_HOST = '127.0.0.1'
IB_PORT = 4001
DEEPSEEK_MODEL = "deepseek-reasoner"

# Generate run ID
RUN_ID = datetime.now().strftime('%Y%m%d_%H%M%S')

# Setup logging
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f'portfolio_reviewer_{RUN_ID}.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [Reviewer] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def get_current_portfolio(ib: IB) -> Dict:
    """Get current portfolio with P&L from IBKR."""
    logger.info("Fetching current portfolio from IBKR...")
    
    ib.reqAccountSummary()
    ib.sleep(1)
    
    portfolio_items = ib.portfolio()
    positions = []
    
    for item in portfolio_items:
        if item.position != 0:
            symbol = item.contract.symbol
            quantity = item.position
            avg_cost = item.averageCost
            current_price = item.marketPrice
            market_value = item.marketValue
            unrealized_pnl = item.unrealizedPNL
            realized_pnl = item.realizedPNL
            
            pnl_pct = (unrealized_pnl / (avg_cost * abs(quantity)) * 100) if avg_cost != 0 else 0
            
            positions.append({
                'symbol': symbol,
                'quantity': quantity,
                'avg_cost': avg_cost,
                'current_price': current_price,
                'market_value': market_value,
                'unrealized_pnl': unrealized_pnl,
                'realized_pnl': realized_pnl,
                'pnl_pct': pnl_pct
            })
    
    # Get account value
    account_values = ib.accountSummary()
    total_value = 0
    for item in account_values:
        if item.tag == 'NetLiquidation':
            total_value = float(item.value)
            break
    
    logger.info(f"Current portfolio: {len(positions)} positions, Total value: ${total_value:,.2f}")
    
    return {
        'positions': positions,
        'total_value': total_value,
        'timestamp': datetime.now().isoformat()
    }


def generate_trade_explanation(
    action: str,
    symbol: str,
    current_position: Optional[Dict],
    new_pick: Optional[Dict],
    llm: ChatOpenAI
) -> str:
    """Generate detailed explanation for a proposed trade using DeepSeek."""
    
    if action == "SELL":
        prompt = f"""You are a portfolio manager explaining why to SELL a position.

Current Position:
- Symbol: {symbol}
- Quantity: {current_position['quantity']}
- Avg Cost: ${current_position['avg_cost']:.2f}
- Current Price: ${current_position['current_price']:.2f}
- Unrealized P&L: ${current_position['unrealized_pnl']:.2f} ({current_position['pnl_pct']:.1f}%)

This position is NOT in this week's top 5 picks from Monte Carlo analysis.

Provide a 3-4 sentence explanation for why we should consider selling this position. Focus on:
1. Current performance (profit/loss)
2. Risk/reward of holding vs reallocating capital
3. Better opportunities available

Be concise and professional."""

    elif action == "BUY":
        prompt = f"""You are a portfolio manager explaining why to BUY a new position.

Proposed Buy:
- Symbol: {symbol}
- Analysis Confidence: {new_pick['confidence']*100:.0f}%
- Reasoning: {new_pick.get('reasoning', 'High growth potential')}

This stock ranked in the top 5 from our Monte Carlo analysis of 232 candidates.

Provide a 3-4 sentence explanation for why we should consider buying this position. Focus on:
1. Key strengths from the analysis
2. Expected return potential
3. How it improves portfolio diversification

Be concise and professional."""

    else:  # HOLD
        prompt = f"""You are a portfolio manager explaining why to HOLD a position.

Current Position:
- Symbol: {symbol}
- Quantity: {current_position['quantity']}
- Unrealized P&L: ${current_position['unrealized_pnl']:.2f} ({current_position['pnl_pct']:.1f}%)
- Analysis Confidence: {new_pick['confidence']*100:.0f}%

This position is BOTH in our current portfolio AND in this week's top 5 picks.

Provide a 2-3 sentence explanation for why we should continue holding this position.

Be concise and professional."""

    try:
        logger.info(f"Generating explanation for {action} {symbol}...")
        response = llm.invoke([HumanMessage(content=prompt)])
        explanation = response.content.strip()
        logger.info(f"Generated explanation for {symbol}")
        return explanation
    except Exception as e:
        logger.error(f"Error generating explanation: {e}")
        return f"Analysis confidence: {new_pick['confidence']*100:.0f}%" if new_pick else "Position not in top picks."


def generate_pdf_report(
    current_portfolio: Dict,
    top_picks: List[Dict],
    proposed_trades: List[Dict],
    run_id: str
) -> str:
    """Generate comprehensive PDF report of proposed trades."""
    
    if not REPORTLAB_AVAILABLE:
        logger.warning("reportlab not available. Skipping PDF generation.")
        return None
    
    # Create proposed_trades directory
    pdf_dir = "proposed_trades"
    os.makedirs(pdf_dir, exist_ok=True)
    
    # Generate filename
    pdf_filename = os.path.join(pdf_dir, f"portfolio_proposal_{run_id}.pdf")
    
    logger.info(f"Generating PDF report: {pdf_filename}")
    
    # Create PDF
    doc = SimpleDocTemplate(pdf_filename, pagesize=letter,
                           topMargin=0.75*inch, bottomMargin=0.75*inch)
    story = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1f4788'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#2c5aa0'),
        spaceAfter=12,
        spaceBefore=20
    )
    
    subheading_style = ParagraphStyle(
        'CustomSubHeading',
        parent=styles['Heading3'],
        fontSize=12,
        textColor=colors.HexColor('#4a4a4a'),
        spaceAfter=8
    )
    
    # Title
    story.append(Paragraph("📊 WEEKLY PORTFOLIO REVIEW", title_style))
    story.append(Paragraph(f"<i>Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</i>",
                          styles['Normal']))
    story.append(Spacer(1, 0.3*inch))
    
    # Executive Summary
    story.append(Paragraph("Executive Summary", heading_style))
    
    buy_count = sum(1 for t in proposed_trades if t['action'] == 'BUY')
    sell_count = sum(1 for t in proposed_trades if t['action'] == 'SELL')
    hold_count = sum(1 for t in proposed_trades if t['action'] == 'HOLD')
    
    summary_data = [
        ['Metric', 'Value'],
        ['Current Positions', str(len(current_portfolio['positions']))],
        ['Portfolio Value', f"${current_portfolio['total_value']:,.2f}"],
        ['Proposed Buys', str(buy_count)],
        ['Proposed Sells', str(sell_count)],
        ['Holdings to Keep', str(hold_count)],
        ['Total Actions', str(len(proposed_trades))]
    ]
    
    summary_table = Table(summary_data, colWidths=[3*inch, 2.5*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5aa0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
    ]))
    
    story.append(summary_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Current Portfolio Section
    story.append(Paragraph("📈 Current Portfolio Holdings", heading_style))
    
    if current_portfolio['positions']:
        total_unrealized = sum(p['unrealized_pnl'] for p in current_portfolio['positions'])
        
        portfolio_data = [['Symbol', 'Qty', 'Avg Cost', 'Current', 'P&L', 'P&L %']]
        
        for pos in current_portfolio['positions']:
            portfolio_data.append([
                pos['symbol'],
                f"{pos['quantity']:.0f}",
                f"${pos['avg_cost']:.2f}",
                f"${pos['current_price']:.2f}",
                f"${pos['unrealized_pnl']:.2f}",
                f"{pos['pnl_pct']:+.1f}%"
            ])
        
        portfolio_table = Table(portfolio_data, colWidths=[1*inch, 0.7*inch, 1*inch, 1*inch, 1*inch, 1*inch])
        portfolio_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5aa0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9)
        ]))
        
        story.append(portfolio_table)
        story.append(Spacer(1, 0.1*inch))
        story.append(Paragraph(f"<b>Total Unrealized P&L: ${total_unrealized:,.2f}</b>",
                              styles['Normal']))
    else:
        story.append(Paragraph("<i>No current positions</i>", styles['Normal']))
    
    story.append(Spacer(1, 0.3*inch))
    
    # Top Picks Section
    story.append(Paragraph("⭐ This Week's Top 5 Picks", heading_style))
    
    picks_data = [['Rank', 'Symbol', 'Confidence', 'Status']]
    
    current_symbols = {pos['symbol'] for pos in current_portfolio['positions']}
    
    for i, pick in enumerate(top_picks, 1):
        status = "HOLD ✓" if pick['ticker'] in current_symbols else "BUY 🆕"
        picks_data.append([
            str(i),
            pick['ticker'],
            f"{pick['confidence']*100:.0f}%",
            status
        ])
    
    picks_table = Table(picks_data, colWidths=[1*inch, 1.5*inch, 1.5*inch, 2*inch])
    picks_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5aa0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9)
    ]))
    
    story.append(picks_table)
    story.append(PageBreak())
    
    # Detailed Trade Proposals
    story.append(Paragraph("🔄 Proposed Trades - Detailed Analysis", heading_style))
    
    for i, trade in enumerate(proposed_trades, 1):
        # Trade header
        action_color = {
            'BUY': colors.HexColor('#28a745'),
            'SELL': colors.HexColor('#dc3545'),
            'HOLD': colors.HexColor('#6c757d')
        }.get(trade['action'], colors.black)
        
        trade_title = f"{i}. {trade['action']} {trade['symbol']}"
        story.append(Paragraph(f"<b><font color='#{action_color.hexval()[2:]}'>{trade_title}</font></b>",
                              subheading_style))
        
        # Trade details
        if trade['action'] == 'BUY':
            pick = trade['new_pick']
            details = [
                f"<b>Confidence Score:</b> {pick['confidence']*100:.0f}%",
                f"<b>Rank:</b> #{[p['ticker'] for p in top_picks].index(pick['ticker']) + 1} of top 5 picks"
            ]
            
        elif trade['action'] == 'SELL':
            pos = trade['current_position']
            details = [
                f"<b>Current Position:</b> {pos['quantity']:.0f} shares @ ${pos['avg_cost']:.2f} avg",
                f"<b>Current Price:</b> ${pos['current_price']:.2f}",
                f"<b>Unrealized P&L:</b> ${pos['unrealized_pnl']:.2f} ({pos['pnl_pct']:+.1f}%)",
                f"<b>Reason:</b> Not in top 5 picks this week"
            ]
            
        else:  # HOLD
            pos = trade['current_position']
            pick = trade['new_pick']
            details = [
                f"<b>Current Position:</b> {pos['quantity']:.0f} shares @ ${pos['avg_cost']:.2f} avg",
                f"<b>Current Price:</b> ${pos['current_price']:.2f}",
                f"<b>Unrealized P&L:</b> ${pos['unrealized_pnl']:.2f} ({pos['pnl_pct']:+.1f}%)",
                f"<b>Confidence Score:</b> {pick['confidence']*100:.0f}%",
                f"<b>Status:</b> Remains in top 5 picks"
            ]
        
        for detail in details:
            story.append(Paragraph(detail, styles['Normal']))
        
        story.append(Spacer(1, 0.1*inch))
        
        # Explanation
        story.append(Paragraph("<b>Analysis:</b>", styles['Normal']))
        explanation_para = Paragraph(trade['explanation'], styles['Normal'])
        story.append(explanation_para)
        
        story.append(Spacer(1, 0.2*inch))
        
        # Separator
        if i < len(proposed_trades):
            story.append(Paragraph("─" * 80, styles['Normal']))
            story.append(Spacer(1, 0.2*inch))
    
    # Approval Section
    story.append(PageBreak())
    story.append(Paragraph("✅ Approval Checklist", heading_style))
    
    story.append(Paragraph(
        "Review this report carefully before approving trades in the system. "
        "Consider the following:",
        styles['Normal']
    ))
    story.append(Spacer(1, 0.1*inch))
    
    checklist = [
        "□ Do the top 5 picks align with current market conditions?",
        "□ Are the buy recommendations affordable within budget constraints?",
        "□ Do sell recommendations make sense given current P&L?",
        "□ Is portfolio diversification maintained or improved?",
        "□ Are there any tax implications for selling positions?",
        "□ Do you have sufficient settled cash to execute buys?"
    ]
    
    for item in checklist:
        story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;{item}", styles['Normal']))
    
    story.append(Spacer(1, 0.3*inch))
    
    story.append(Paragraph(
        "<b>Next Steps:</b> Run the portfolio reviewer to approve/reject each trade, "
        "then the portfolio manager will execute approved trades.",
        styles['Normal']
    ))
    
    # Build PDF
    doc.build(story)
    
    logger.info(f"PDF report generated: {pdf_filename}")
    return pdf_filename


def display_portfolio_review(current_portfolio: Dict, top_picks: List[Dict], llm: ChatOpenAI):
    """Display comprehensive portfolio review with proposed trades."""
    
    print("\n" + "="*80)
    print("📊 WEEKLY PORTFOLIO REVIEW")
    print("="*80)
    
    # Current Portfolio
    print("\n📈 CURRENT PORTFOLIO:")
    print("-" * 80)
    
    if not current_portfolio['positions']:
        print("No current positions.")
    else:
        total_unrealized = 0
        for pos in current_portfolio['positions']:
            print(f"\n{pos['symbol']}:")
            print(f"  Quantity: {pos['quantity']}")
            print(f"  Avg Cost: ${pos['avg_cost']:.2f}")
            print(f"  Current: ${pos['current_price']:.2f}")
            print(f"  P&L: ${pos['unrealized_pnl']:.2f} ({pos['pnl_pct']:+.1f}%)")
            total_unrealized += pos['unrealized_pnl']
        
        print(f"\n{'─'*80}")
        print(f"Total Unrealized P&L: ${total_unrealized:,.2f}")
        print(f"Portfolio Value: ${current_portfolio['total_value']:,.2f}")
    
    # Top Picks This Week
    print("\n\n⭐ THIS WEEK'S TOP 5 PICKS:")
    print("-" * 80)
    for i, pick in enumerate(top_picks, 1):
        print(f"{i}. {pick['ticker']} (Confidence: {pick['confidence']*100:.0f}%)")
    
    # Proposed Trades
    print("\n\n🔄 PROPOSED TRADES:")
    print("="*80)
    
    current_symbols = {pos['symbol'] for pos in current_portfolio['positions']}
    top_pick_symbols = {pick['ticker'] for pick in top_picks}
    
    proposed_trades = []
    
    # Sells: Current positions not in top picks
    for pos in current_portfolio['positions']:
        if pos['symbol'] not in top_pick_symbols:
            explanation = generate_trade_explanation(
                "SELL", pos['symbol'], pos, None, llm
            )
            proposed_trades.append({
                'action': 'SELL',
                'symbol': pos['symbol'],
                'quantity': pos['quantity'],
                'current_position': pos,
                'explanation': explanation
            })
    
    # Buys: Top picks not in current portfolio
    for pick in top_picks:
        if pick['ticker'] not in current_symbols:
            explanation = generate_trade_explanation(
                "BUY", pick['ticker'], None, pick, llm
            )
            proposed_trades.append({
                'action': 'BUY',
                'symbol': pick['ticker'],
                'new_pick': pick,
                'explanation': explanation
            })
    
    # Holds: Positions in both
    for pos in current_portfolio['positions']:
        if pos['symbol'] in top_pick_symbols:
            pick = next(p for p in top_picks if p['ticker'] == pos['symbol'])
            explanation = generate_trade_explanation(
                "HOLD", pos['symbol'], pos, pick, llm
            )
            proposed_trades.append({
                'action': 'HOLD',
                'symbol': pos['symbol'],
                'quantity': pos['quantity'],
                'current_position': pos,
                'new_pick': pick,
                'explanation': explanation
            })
    
    # Display trades
    if not proposed_trades:
        print("\nNo trades proposed. Portfolio matches top picks.")
    else:
        for i, trade in enumerate(proposed_trades, 1):
            print(f"\n{i}. {trade['action']} {trade['symbol']}")
            print(f"{'-'*80}")
            
            if trade['action'] == 'SELL':
                pos = trade['current_position']
                print(f"Current Position:")
                print(f"  Quantity: {pos['quantity']}")
                print(f"  P&L: ${pos['unrealized_pnl']:.2f} ({pos['pnl_pct']:+.1f}%)")
                print(f"\nReason:")
                print(f"  {trade['explanation']}")
            
            elif trade['action'] == 'BUY':
                pick = trade['new_pick']
                print(f"Proposed Buy:")
                print(f"  Confidence: {pick['confidence']*100:.0f}%")
                print(f"\nReason:")
                print(f"  {trade['explanation']}")
            
            elif trade['action'] == 'HOLD':
                pos = trade['current_position']
                pick = trade['new_pick']
                print(f"Current Position:")
                print(f"  Quantity: {pos['quantity']}")
                print(f"  P&L: ${pos['unrealized_pnl']:.2f} ({pos['pnl_pct']:+.1f}%)")
                print(f"  Confidence: {pick['confidence']*100:.0f}%")
                print(f"\nReason:")
                print(f"  {trade['explanation']}")
    
    return proposed_trades


def get_user_approvals(proposed_trades: List[Dict]) -> Dict[str, bool]:
    """Get user approval for each proposed trade."""
    
    print("\n" + "="*80)
    print("⚠️  APPROVAL REQUIRED")
    print("="*80)
    print("\nReview each trade and approve/reject:")
    print("  - Type 'y' or 'yes' to APPROVE")
    print("  - Type 'n' or 'no' to REJECT")
    print("  - Type 'all' to approve ALL trades")
    print("  - Type 'none' to reject ALL trades")
    print("="*80 + "\n")
    
    approvals = {}
    
    for i, trade in enumerate(proposed_trades, 1):
        action = trade['action']
        symbol = trade['symbol']
        
        print(f"\n[{i}/{len(proposed_trades)}] {action} {symbol}")
        
        while True:
            response = input(f"  Approve? (y/n/all/none): ").strip().lower()
            
            if response in ['all']:
                # Approve all remaining
                for t in proposed_trades[i-1:]:
                    approvals[f"{t['action']}_{t['symbol']}"] = True
                print("  ✅ Approved all remaining trades")
                return approvals
            
            elif response in ['none']:
                # Reject all remaining
                for t in proposed_trades[i-1:]:
                    approvals[f"{t['action']}_{t['symbol']}"] = False
                print("  ❌ Rejected all remaining trades")
                return approvals
            
            elif response in ['y', 'yes']:
                approvals[f"{action}_{symbol}"] = True
                print(f"  ✅ Approved: {action} {symbol}")
                break
            
            elif response in ['n', 'no']:
                approvals[f"{action}_{symbol}"] = False
                print(f"  ❌ Rejected: {action} {symbol}")
                break
            
            else:
                print("  Invalid input. Please enter y/n/all/none")
    
    return approvals


def save_approval_decisions(proposed_trades: List[Dict], approvals: Dict[str, bool]):
    """Save approval decisions to file for portfolio manager to execute."""
    
    approved_trades = []
    
    for trade in proposed_trades:
        key = f"{trade['action']}_{trade['symbol']}"
        if approvals.get(key, False):
            approved_trades.append({
                'action': trade['action'],
                'symbol': trade['symbol'],
                'quantity': trade.get('quantity'),
                'approved_at': datetime.now().isoformat()
            })
    
    # Save to shared state
    decision_file = "shared_state/approved_trades.json"
    os.makedirs(os.path.dirname(decision_file), exist_ok=True)
    
    with open(decision_file, 'w') as f:
        json.dump({
            'approved_trades': approved_trades,
            'timestamp': datetime.now().isoformat(),
            'total_proposed': len(proposed_trades),
            'total_approved': len(approved_trades)
        }, f, indent=2)
    
    logger.info(f"Saved {len(approved_trades)} approved trades to {decision_file}")
    
    print("\n" + "="*80)
    print("✅ APPROVAL SUMMARY")
    print("="*80)
    print(f"Total trades proposed: {len(proposed_trades)}")
    print(f"Approved: {len(approved_trades)}")
    print(f"Rejected: {len(proposed_trades) - len(approved_trades)}")
    print("="*80 + "\n")


def main():
    """Main review workflow."""
    
    logger.info("="*80)
    logger.info("PHASE 3.5: PORTFOLIO REVIEW & APPROVAL - Starting")
    logger.info("="*80)
    
    # Check phase state
    state = read_state('phase_state')
    if state.get('current_phase') != 'analysis_complete':
        logger.error(f"Wrong phase. Expected 'analysis_complete', got '{state.get('current_phase')}'")
        print("❌ Error: Analysis must be completed first")
        return 1
    
    # Load top picks
    top_picks = state.get('top_picks', [])
    if not top_picks:
        logger.error("No top picks found in state")
        print("❌ Error: No top picks available for review")
        return 1
    
    logger.info(f"Loaded {len(top_picks)} top picks")
    
    # Initialize LLM for explanations
    logger.info("Initializing DeepSeek for trade explanations...")
    llm = ChatOpenAI(
        model=DEEPSEEK_MODEL,
        temperature=0.1,
        openai_api_key=os.getenv('DEEPSEEK_API_KEY'),
        openai_api_base='https://api.deepseek.com'
    )
    
    # Connect to IBKR
    logger.info(f"Connecting to IBKR at {IB_HOST}:{IB_PORT}...")
    ib = IB()
    
    try:
        ib.connect(IB_HOST, IB_PORT, clientId=1)
        logger.info("Connected to IBKR")
        
        # Get current portfolio
        current_portfolio = get_current_portfolio(ib)
        
        # Display review and get approvals
        proposed_trades = display_portfolio_review(current_portfolio, top_picks, llm)
        
        if proposed_trades:
            # Generate PDF report FIRST (before approval)
            pdf_path = generate_pdf_report(current_portfolio, top_picks, proposed_trades, RUN_ID)
            
            if pdf_path:
                print("\n" + "="*80)
                print(f"📄 PDF REPORT GENERATED: {pdf_path}")
                print("="*80)
                print("\n✅ Review the PDF report before approving trades!")
                print("   The report contains detailed analysis of all proposed trades.")
                print(f"\n   Location: {os.path.abspath(pdf_path)}")
                print("\n" + "="*80)
            
            approvals = get_user_approvals(proposed_trades)
            save_approval_decisions(proposed_trades, approvals)
            
            # Update phase state
            write_state('phase_state', {
                'current_phase': 'review_complete',
                'review_timestamp': datetime.now().isoformat()
            })
            
            logger.info("Review complete. Approved trades saved.")
            print("\n✅ Review complete. Run portfolio manager to execute approved trades.")
        else:
            logger.info("No trades to review")
            print("\n✅ No trades needed. Portfolio matches top picks.")
        
    except Exception as e:
        logger.error(f"Error during review: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        return 1
    
    finally:
        if ib.isConnected():
            ib.disconnect()
            logger.info("Disconnected from IBKR")
    
    logger.info("="*80)
    logger.info("PHASE 3.5: PORTFOLIO REVIEW & APPROVAL - Complete")
    logger.info("="*80)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
