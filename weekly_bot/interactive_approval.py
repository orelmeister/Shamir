"""
Interactive Approval Script for Form 4 Strategy
Loads existing analysis results and provides interactive Q&A for each position
"""

import os
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dotenv import load_dotenv

# LangChain imports
from langchain_deepseek import ChatDeepSeek
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

# IBKR imports
from ib_insync import IB, Stock, MarketOrder, util

# Load environment
load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

class InteractiveApproval:
    """Interactive approval system with LLM Q&A capabilities"""
    
    def __init__(self):
        # Initialize LLM
        self.llm = None
        self.llm_available = False
        
        if DEEPSEEK_API_KEY:
            try:
                self.llm = ChatDeepSeek(
                    model="deepseek-reasoner",
                    temperature=0.1
                )
                self.llm_available = True
                print("[+] LLM Available: DeepSeek Reasoner ready for Q&A")
            except Exception as e:
                print(f"[!] DeepSeek initialization failed: {e}")
        
        if not self.llm and GOOGLE_API_KEY:
            try:
                self.llm = ChatGoogleGenerativeAI(
                    model="gemini-2.5-pro",
                    temperature=0.1
                )
                self.llm_available = True
                print("[+] LLM Available: Gemini 2.5 Pro ready for Q&A")
            except Exception as e:
                print(f"[!] Gemini initialization failed: {e}")
        
        if not self.llm:
            print("[!] No LLM available - Q&A features disabled")
        
        # IBKR connection
        self.ib = None
        self.ibkr_connected = False
    
    def recalculate_position_sizes(self, approved_positions: List[Dict], total_capital: float) -> List[Dict]:
        """
        Recalculate position sizes AFTER approval to deploy full capital
        
        This fixes the bug where rejecting positions wasted capital.
        Example: 4 positions @ $250 each → User approves 2 → Should be $500 each (not $250)
        
        Args:
            approved_positions: List of approved position dicts
            total_capital: Total capital to deploy
        
        Returns: Updated list with recalculated shares and costs
        """
        if not approved_positions:
            return []
        
        num_approved = len(approved_positions)
        dollars_per_position = total_capital / num_approved
        
        print(f"\n{'='*80}")
        print(f"♻️  RECALCULATING POSITION SIZES")
        print(f"{'='*80}")
        print(f"Capital: ${total_capital:.2f}")
        print(f"Approved Positions: {num_approved}")
        print(f"Allocation per Position: ${dollars_per_position:.2f}")
        print(f"{'='*80}\n")
        
        for position in approved_positions:
            symbol = position['symbol']
            price = position['price']
            old_shares = position['position']['shares']
            old_cost = position['position']['actual_dollars']
            
            # Recalculate shares
            new_shares = int(dollars_per_position / price)
            new_cost = new_shares * price
            
            # Update position dict
            position['position'] = {
                'target_dollars': dollars_per_position,
                'shares': new_shares,
                'actual_dollars': new_cost,
                'price': price
            }
            
            # Log change
            print(f"  {symbol}: {old_shares} → {new_shares} shares (${old_cost:.2f} → ${new_cost:.2f})")
        
        total_allocated = sum(p['position']['actual_dollars'] for p in approved_positions)
        print(f"\n✅ Total Allocated: ${total_allocated:.2f} / ${total_capital:.2f}")
        print(f"{'='*80}\n")
        
        return approved_positions
    
    def connect_to_ibkr(self) -> bool:
        """Connect to IBKR for order execution"""
        try:
            self.ib = IB()
            print("\n[*] Connecting to IBKR at 127.0.0.1:4001...")
            util.run(self.ib.connectAsync('127.0.0.1', 4001, clientId=10))
            self.ib.reqMarketDataType(3)
            self.ibkr_connected = True
            print("[+] IBKR Connected: Ready for order execution\n")
            return True
        except Exception as e:
            print(f"[!] IBKR Connection failed: {e}")
            print("[!] Automatic trading disabled\n")
            return False
    
    def disconnect_from_ibkr(self):
        """Disconnect from IBKR"""
        if self.ib and self.ibkr_connected:
            try:
                self.ib.disconnect()
                print("\n[*] Disconnected from IBKR")
            except:
                pass
    
    def load_latest_results(self) -> Optional[Dict]:
        """Load the most recent Form 4 analysis results"""
        reports_dir = Path("weekly_bot/form4_reports")
        
        # Find all position JSON files
        json_files = sorted(reports_dir.glob("form4_positions_*.json"), reverse=True)
        
        if not json_files:
            print("[!] ERROR: No analysis results found!")
            print("    Run the main script first: python weekly_bot/05_form4_strategy.py")
            return None
        
        latest_file = json_files[0]
        print(f"[+] Loading results from: {latest_file.name}")
        
        with open(latest_file, 'r') as f:
            return json.load(f)
    
    def ask_llm_about_stock(self, position: Dict):
        """Interactive Q&A session about a specific stock"""
        if not self.llm_available:
            print("\n[!] Q&A disabled - no LLM available")
            return
        
        symbol = position['symbol']
        company = position['company']
        
        # Build context for LLM
        context = f"""
Stock: {symbol} - {company}
Sector: {position['sector']}
Market Cap: ${position['market_cap']/1_000_000:.0f}M
Price: ${position['price']:.2f}

INSIDER SIGNALS:
- Total Signals: {position['total_signals']}
- Quality Score: {position['signal_quality_score']:.2f}/3.0
- Politicians: {position['politician_signals']}
- Directors: {position['director_signals']}
- Officers: {position['officer_signals']}
- Timing: {position['timing_status']}
- Days Since Last Trade: {position['days_since_last_trade']}
- Price Movement: {position['price_movement_pct']:.2f}%

ANALYSIS:
Confidence: {position['confidence']:.1%}

Reasoning: {position['reasoning']}

Bull Case: {position['bull_case']}

Bear Case: {position['bear_case']}

Hold Period: {position['hold_period_days']} days

POSITION:
Shares: {position['position']['shares']}
Cost: ${position['position']['actual_dollars']:.2f}
"""
        
        print(f"\n{'='*80}")
        print(f"Q&A SESSION: {symbol} - {company}")
        print(f"{'='*80}")
        print("\nType your questions about this stock.")
        print("Commands:")
        print("  - Type your question and press Enter")
        print("  - Type 'done' to finish Q&A")
        print("  - Type 'summary' to see full analysis again")
        print(f"{'='*80}\n")
        
        while True:
            try:
                question = input(f"{symbol} Question: ").strip()
                
                if not question:
                    continue
                
                if question.lower() == 'done':
                    break
                
                if question.lower() == 'summary':
                    print(f"\n{context}")
                    continue
                
                # Ask LLM
                print(f"\n[Thinking...]")
                
                system_prompt = """You are an expert stock analyst helping an investor understand 
an insider trading opportunity. Answer questions concisely and directly based on the 
analysis provided. Focus on practical investment considerations."""
                
                user_prompt = f"""Context about the stock:
{context}

Investor's question: {question}

Provide a clear, concise answer focusing on investment implications."""
                
                messages = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt)
                ]
                
                response = self.llm.invoke(messages)
                answer = response.content
                
                print(f"\n[Answer]:")
                print(f"{answer}\n")
                
            except KeyboardInterrupt:
                print("\n[*] Q&A interrupted")
                break
            except Exception as e:
                print(f"[!] Error: {e}\n")
    
    def display_position(self, position: Dict, index: int, total: int):
        """Display full position details (not truncated)"""
        print(f"\n{'='*80}")
        print(f"POSITION #{index}/{total}: {position['symbol']} - {position['company']}")
        print(f"{'='*80}")
        print(f"\nBASIC INFO:")
        print(f"  Sector: {position['sector']}")
        print(f"  Market Cap: ${position['market_cap']/1_000_000:.0f}M")
        print(f"  Price: ${position['price']:.2f}")
        
        print(f"\nINSIDER SIGNALS:")
        print(f"  Total Signals: {position['total_signals']}")
        print(f"  Quality Score: {position['signal_quality_score']:.2f}/3.0")
        print(f"  Politicians: {position['politician_signals']}")
        print(f"  Directors: {position['director_signals']}")
        print(f"  Officers: {position['officer_signals']}")
        print(f"  Timing: {position['timing_status']}")
        print(f"  Days Since Last Trade: {position['days_since_last_trade']}")
        print(f"  Price Movement: {position['price_movement_pct']:+.2f}%")
        
        print(f"\nSOURCE BREAKDOWN:")
        sources = position['source_breakdown']
        if sources.get('senate', 0) > 0:
            print(f"  - Senate: {sources['senate']} purchases")
        if sources.get('house', 0) > 0:
            print(f"  - House: {sources['house']} purchases")
        if sources.get('insider', 0) > 0:
            print(f"  - Form 4: {sources['insider']} transactions")
        if sources.get('latest', 0) > 0:
            print(f"  - Latest Insider: {sources['latest']} acquisitions")
        
        print(f"\nANALYSIS:")
        print(f"  Confidence: {position['confidence']:.1%}")
        print(f"  Hold Period: {position['hold_period_days']} days")
        
        print(f"\n  REASONING (FULL):")
        print(f"  {position['reasoning']}")
        
        print(f"\n  BULL CASE (FULL):")
        print(f"  {position['bull_case']}")
        
        print(f"\n  BEAR CASE (FULL):")
        print(f"  {position['bear_case']}")
        
        print(f"\nPOSITION DETAILS:")
        print(f"  Shares: {position['position']['shares']}")
        print(f"  Cost: ${position['position']['actual_dollars']:.2f}")
        print(f"  Per Share: ${position['position']['price']:.2f}")
        print(f"{'='*80}")
    
    def get_approval(self, position: Dict, index: int, total: int) -> bool:
        """Get user approval for a position with Q&A option"""
        self.display_position(position, index, total)
        
        while True:
            print(f"\nOPTIONS:")
            print(f"  y/yes   - APPROVE this position")
            print(f"  n/no    - REJECT this position")
            print(f"  q/ask   - ASK QUESTIONS about this stock (LLM Q&A)")
            print(f"  all     - APPROVE ALL remaining positions")
            print(f"  none    - REJECT ALL remaining positions")
            
            response = input(f"\nDecision for {position['symbol']}: ").strip().lower()
            
            if response in ['y', 'yes']:
                print(f"[+] {position['symbol']} APPROVED")
                return True
            
            elif response in ['n', 'no']:
                print(f"[-] {position['symbol']} REJECTED")
                return False
            
            elif response in ['q', 'ask', 'question']:
                if self.llm_available:
                    self.ask_llm_about_stock(position)
                    # After Q&A, show position again
                    self.display_position(position, index, total)
                else:
                    print("\n[!] Q&A not available - no LLM configured")
            
            elif response == 'all':
                return 'approve_all'
            
            elif response == 'none':
                return 'reject_all'
            
            else:
                print("[!] Invalid response. Please use: y/n/q/all/none")
    
    def execute_order(self, position: Dict) -> bool:
        """Execute market order via IBKR"""
        if not self.ibkr_connected:
            print(f"[!] Cannot execute {position['symbol']} - IBKR not connected")
            return False
        
        try:
            symbol = position['symbol']
            shares = position['position']['shares']
            
            # Create contract
            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            
            # Place market order
            order = MarketOrder('BUY', shares)
            trade = self.ib.placeOrder(contract, order)
            
            print(f"[*] Order placed for {symbol}: BUY {shares} shares")
            
            # Wait for fill (up to 30 seconds)
            for _ in range(30):
                self.ib.sleep(1)
                if trade.orderStatus.status == 'Filled':
                    fill_price = trade.orderStatus.avgFillPrice
                    print(f"[+] {symbol} FILLED at ${fill_price:.2f}")
                    return True
            
            print(f"[!] {symbol} order timeout - check TWS for status")
            return False
            
        except Exception as e:
            print(f"[!] Error executing {symbol}: {e}")
            return False
    
    def run(self):
        """Main interactive approval flow"""
        print("\n" + "="*80)
        print("FORM 4 STRATEGY - INTERACTIVE APPROVAL")
        print("="*80)
        
        # Load results
        results = self.load_latest_results()
        if not results:
            return
        
        positions = results['positions']
        
        print(f"\nGenerated: {results['generated_at']}")
        print(f"Strategy: {results['strategy']}")
        print(f"Lookback: {results['lookback_days']} days")
        print(f"Capital: ${results['capital']:.2f}")
        print(f"Positions: {len(positions)}")
        
        # Connect to IBKR
        self.connect_to_ibkr()
        
        # Process each position
        approvals = {}
        approved_count = 0
        
        try:
            for i, position in enumerate(positions, 1):
                symbol = position['symbol']
                
                approval = self.get_approval(position, i, len(positions))
                
                if approval == 'approve_all':
                    # Approve this and all remaining
                    for p in positions[i-1:]:
                        approvals[p['symbol']] = True
                        approved_count += 1
                    print(f"\n[+] Approved all {len(positions) - i + 1} remaining positions")
                    break
                
                elif approval == 'reject_all':
                    # Reject this and all remaining
                    for p in positions[i-1:]:
                        approvals[p['symbol']] = False
                    print(f"\n[-] Rejected all {len(positions) - i + 1} remaining positions")
                    break
                
                else:
                    approvals[symbol] = approval
                    if approval:
                        approved_count += 1
            
            # Summary
            print(f"\n{'='*80}")
            print("APPROVAL SUMMARY")
            print(f"{'='*80}")
            print(f"Approved: {approved_count}/{len(positions)}")
            print(f"Rejected: {len(positions) - approved_count}/{len(positions)}")
            
            if approved_count > 0:
                # Recalculate position sizes for approved positions only (FIX: Deploy full capital)
                approved_positions = [p for p in positions if approvals.get(p['symbol'], False)]
                total_capital = results.get('capital', 1000.0)
                approved_positions = self.recalculate_position_sizes(approved_positions, total_capital)
                
                # Update positions list with recalculated values
                for updated_pos in approved_positions:
                    for i, original_pos in enumerate(positions):
                        if original_pos['symbol'] == updated_pos['symbol']:
                            positions[i] = updated_pos
                            break
                
                print(f"\nApproved positions:")
                for symbol, approved in approvals.items():
                    if approved:
                        pos = next(p for p in positions if p['symbol'] == symbol)
                        print(f"  - {symbol}: {pos['position']['shares']} shares @ ${pos['price']:.2f} = ${pos['position']['actual_dollars']:.2f}")
                
                # Execute orders
                if self.ibkr_connected:
                    execute = input(f"\nExecute {approved_count} orders via IBKR? (y/n): ").strip().lower()
                    if execute in ['y', 'yes']:
                        print(f"\n{'='*80}")
                        print("EXECUTING ORDERS")
                        print(f"{'='*80}\n")
                        
                        for symbol, approved in approvals.items():
                            if approved:
                                pos = next(p for p in positions if p['symbol'] == symbol)
                                self.execute_order(pos)
                    else:
                        print("\n[*] Order execution cancelled")
                else:
                    print("\n[!] Cannot execute - IBKR not connected")
                    print("    Orders saved in approval file for manual execution")
            
            # Save approvals
            results['approvals'] = approvals
            results['approved_count'] = approved_count
            results['approval_timestamp'] = datetime.now().isoformat()
            
            output_file = Path(f"weekly_bot/form4_reports/approved_positions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            with open(output_file, 'w') as f:
                json.dump(results, f, indent=2)
            
            print(f"\n[+] Approvals saved to: {output_file.name}")
            
        finally:
            self.disconnect_from_ibkr()
        
        print(f"\n{'='*80}")
        print("APPROVAL SESSION COMPLETE")
        print(f"{'='*80}\n")


def main():
    approval = InteractiveApproval()
    approval.run()


if __name__ == "__main__":
    main()
