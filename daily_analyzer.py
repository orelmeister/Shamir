"""
Daily Performance Analyzer
Analyzes trading performance after each day and generates insights
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from performance_tracker import PerformanceTracker
from langchain_deepseek import ChatDeepSeek
from langchain_google_genai import ChatGoogleGenerativeAI
import os
from dotenv import load_dotenv

load_dotenv()

class DailyPerformanceAnalyzer:
    """Analyzes daily trading performance and generates actionable insights"""
    
    def __init__(self, log_file, performance_tracker=None):
        self.log_file = log_file
        self.performance_tracker = performance_tracker or PerformanceTracker()
        self.logger = logging.getLogger(__name__)
        
        # Initialize LLM for analysis
        try:
            self.llm = ChatDeepSeek(
                model="deepseek-reasoner",
                api_key=os.getenv("DEEPSEEK_API_KEY"),
                temperature=0.3
            )
        except:
            self.llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash-exp",
                api_key=os.getenv("GOOGLE_API_KEY"),
                temperature=0.3
            )
    
    def analyze_day(self, date=None):
        """Analyze performance for a specific date"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        self.logger.info(f"Analyzing performance for {date}")
        
        # Parse log file to extract trade data
        trades = self._extract_trades_from_log()
        
        if not trades:
            self.logger.warning(f"No trades found for {date}")
            return None
        
        # Calculate performance metrics
        metrics = self._calculate_metrics(trades)
        
        # Store in database
        self.performance_tracker.update_daily_summary(date, metrics)
        
        # Store individual trades
        for trade in trades:
            self.performance_tracker.log_trade(trade)
        
        # Generate LLM insights
        insights = self._generate_insights(metrics, trades)
        
        # Store insights
        for insight in insights:
            self.performance_tracker.log_insight(
                insight_type=insight['type'],
                content=insight['content'],
                actionable=insight.get('actionable', False)
            )
        
        # Print summary
        self._print_summary(metrics, insights)
        
        return {
            'metrics': metrics,
            'insights': insights
        }
    
    def _extract_trades_from_log(self):
        """Extract trade data from JSON log file"""
        trades = []
        positions = {}  # Track open positions
        
        try:
            with open(self.log_file, 'r') as f:
                for line in f:
                    try:
                        log_entry = json.loads(line.strip())
                        message = log_entry.get('message', '')
                        timestamp = log_entry.get('timestamp', '')
                        
                        # Parse BOUGHT messages
                        if 'BOUGHT' in message:
                            parts = message.split()
                            if len(parts) >= 6:
                                quantity = int(parts[1])
                                ticker = parts[4]
                                price = float(parts[6].replace('$', '').replace(',', ''))
                                
                                # Store position
                                positions[ticker] = {
                                    'ticker': ticker,
                                    'action': 'BUY',
                                    'quantity': quantity,
                                    'entry_price': price,
                                    'entry_time': timestamp,
                                    'date': datetime.now().strftime('%Y-%m-%d')
                                }
                        
                        # Parse SOLD messages
                        elif 'SOLD' in message:
                            parts = message.split()
                            if len(parts) >= 6:
                                quantity = int(parts[1])
                                ticker = parts[4]
                                price = float(parts[6].replace('$', '').replace(',', ''))
                                
                                # Calculate P&L if we have entry
                                if ticker in positions:
                                    entry = positions[ticker]
                                    pnl = (price - entry['entry_price']) * quantity
                                    pnl_percent = ((price - entry['entry_price']) / entry['entry_price']) * 100
                                    
                                    # Calculate hold time
                                    try:
                                        entry_dt = datetime.fromisoformat(entry['entry_time'].replace('Z', '+00:00'))
                                        exit_dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                                        hold_time_seconds = int((exit_dt - entry_dt).total_seconds())
                                    except:
                                        hold_time_seconds = 0
                                    
                                    # Determine exit reason
                                    if 'profit target' in message.lower():
                                        exit_reason = 'profit_target'
                                    elif 'stop loss' in message.lower():
                                        exit_reason = 'stop_loss'
                                    elif 'market close' in message.lower() or '4:00 pm' in message.lower():
                                        exit_reason = 'market_close'
                                    else:
                                        exit_reason = 'manual'
                                    
                                    trade = {
                                        'date': entry['date'],
                                        'timestamp': timestamp,
                                        'ticker': ticker,
                                        'action': 'SELL',
                                        'quantity': quantity,
                                        'price': price,
                                        'total_value': price * quantity,
                                        'pnl': pnl,
                                        'pnl_percent': pnl_percent,
                                        'hold_time_seconds': hold_time_seconds,
                                        'entry_time': entry['entry_time'],
                                        'exit_time': timestamp,
                                        'entry_price': entry['entry_price'],
                                        'exit_price': price,
                                        'exit_reason': exit_reason
                                    }
                                    
                                    trades.append(trade)
                                    del positions[ticker]
                    
                    except json.JSONDecodeError:
                        continue
        
        except FileNotFoundError:
            self.logger.error(f"Log file not found: {self.log_file}")
        
        return trades
    
    def _calculate_metrics(self, trades):
        """Calculate performance metrics from trades"""
        if not trades:
            return {}
        
        total_trades = len(trades)
        profitable_trades = sum(1 for t in trades if t['pnl'] > 0)
        losing_trades = total_trades - profitable_trades
        
        total_pnl = sum(t['pnl'] for t in trades)
        win_rate = (profitable_trades / total_trades) * 100 if total_trades > 0 else 0
        
        profits = [t['pnl'] for t in trades if t['pnl'] > 0]
        losses = [t['pnl'] for t in trades if t['pnl'] < 0]
        
        avg_profit = sum(profits) / len(profits) if profits else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        
        avg_hold_time = sum(t['hold_time_seconds'] for t in trades) / total_trades if total_trades > 0 else 0
        
        # Best and worst trades
        best_trade = max(trades, key=lambda t: t['pnl'])
        worst_trade = min(trades, key=lambda t: t['pnl'])
        
        # Exit reasons breakdown
        exit_reasons = {}
        for trade in trades:
            reason = trade.get('exit_reason', 'unknown')
            exit_reasons[reason] = exit_reasons.get(reason, 0) + 1
        
        return {
            'total_trades': total_trades,
            'profitable_trades': profitable_trades,
            'losing_trades': losing_trades,
            'total_pnl': round(total_pnl, 2),
            'win_rate': round(win_rate, 2),
            'avg_profit': round(avg_profit, 2),
            'avg_loss': round(avg_loss, 2),
            'avg_hold_time_seconds': int(avg_hold_time),
            'best_trade_ticker': best_trade['ticker'],
            'best_trade_pnl': round(best_trade['pnl'], 2),
            'worst_trade_ticker': worst_trade['ticker'],
            'worst_trade_pnl': round(worst_trade['pnl'], 2),
            'exit_reasons': exit_reasons
        }
    
    def _generate_insights(self, metrics, trades):
        """Use LLM to generate actionable insights"""
        
        prompt = f"""
        Analyze today's day trading performance and provide specific, actionable insights.
        
        PERFORMANCE METRICS:
        - Total Trades: {metrics['total_trades']}
        - Win Rate: {metrics['win_rate']}%
        - Total P&L: ${metrics['total_pnl']}
        - Average Profit: ${metrics['avg_profit']}
        - Average Loss: ${metrics['avg_loss']}
        - Average Hold Time: {metrics['avg_hold_time_seconds']} seconds ({metrics['avg_hold_time_seconds']//60} minutes)
        - Best Trade: {metrics['best_trade_ticker']} (${metrics['best_trade_pnl']})
        - Worst Trade: {metrics['worst_trade_ticker']} (${metrics['worst_trade_pnl']})
        - Exit Reasons: {metrics['exit_reasons']}
        
        INDIVIDUAL TRADES:
        {json.dumps([{
            'ticker': t['ticker'],
            'pnl': t['pnl'],
            'pnl_percent': t['pnl_percent'],
            'hold_time_minutes': t['hold_time_seconds']//60,
            'exit_reason': t['exit_reason']
        } for t in trades], indent=2)}
        
        Provide analysis in the following categories:
        
        1. WHAT WORKED WELL (successes to repeat)
        2. WHAT DIDN'T WORK (failures to avoid)
        3. PARAMETER ADJUSTMENTS (specific changes to profit_target, stop_loss, ATR_threshold, etc.)
        4. STRATEGY IMPROVEMENTS (new rules or filters to add)
        5. RISK MANAGEMENT (position sizing, diversification insights)
        
        Be specific and actionable. For parameter adjustments, provide exact numbers.
        Format as JSON array with objects containing: type, content, actionable (boolean)
        
        Example:
        [
            {{"type": "success", "content": "Profit targets worked well - 70% of wins hit the 1.4% target", "actionable": false}},
            {{"type": "failure", "content": "Stop losses too tight - 3 trades stopped out before recovering", "actionable": true}},
            {{"type": "parameter", "content": "Increase stop_loss from 0.8% to 1.0% to reduce premature exits", "actionable": true}},
            {{"type": "strategy", "content": "Avoid trading after 2 PM - all afternoon trades were losses", "actionable": true}}
        ]
        """
        
        try:
            response = self.llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            
            # Try to parse JSON from response
            import re
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                insights = json.loads(json_match.group())
                return insights
            else:
                # Fallback: create basic insights
                return self._create_fallback_insights(metrics)
        
        except Exception as e:
            self.logger.warning(f"Failed to generate LLM insights: {e}")
            return self._create_fallback_insights(metrics)
    
    def _create_fallback_insights(self, metrics):
        """Create basic insights without LLM"""
        insights = []
        
        # Win rate analysis
        if metrics['win_rate'] > 60:
            insights.append({
                'type': 'success',
                'content': f"Strong win rate of {metrics['win_rate']}% - strategy is working well",
                'actionable': False
            })
        elif metrics['win_rate'] < 40:
            insights.append({
                'type': 'failure',
                'content': f"Low win rate of {metrics['win_rate']}% - need to be more selective",
                'actionable': True
            })
        
        # P&L analysis
        if metrics['total_pnl'] > 0:
            insights.append({
                'type': 'success',
                'content': f"Profitable day with ${metrics['total_pnl']} total profit",
                'actionable': False
            })
        else:
            insights.append({
                'type': 'failure',
                'content': f"Losing day with ${metrics['total_pnl']} total loss",
                'actionable': True
            })
        
        # Risk/reward analysis
        if abs(metrics['avg_profit']) > abs(metrics['avg_loss']) * 1.5:
            insights.append({
                'type': 'success',
                'content': f"Good risk/reward ratio - avg profit ${metrics['avg_profit']} vs avg loss ${metrics['avg_loss']}",
                'actionable': False
            })
        
        return insights
    
    def _print_summary(self, metrics, insights):
        """Print formatted summary to console"""
        print("\n" + "="*80)
        print("📊 DAILY TRADING PERFORMANCE ANALYSIS")
        print("="*80)
        
        print(f"\n📈 METRICS:")
        print(f"  Total Trades: {metrics['total_trades']}")
        print(f"  Win Rate: {metrics['win_rate']}%")
        print(f"  Total P&L: ${metrics['total_pnl']}")
        print(f"  Avg Profit: ${metrics['avg_profit']} | Avg Loss: ${metrics['avg_loss']}")
        print(f"  Avg Hold Time: {metrics['avg_hold_time_seconds']//60} minutes")
        print(f"  Best: {metrics['best_trade_ticker']} (${metrics['best_trade_pnl']})")
        print(f"  Worst: {metrics['worst_trade_ticker']} (${metrics['worst_trade_pnl']})")
        
        print(f"\n💡 INSIGHTS:")
        for insight in insights:
            emoji = "✅" if insight['type'] == 'success' else "⚠️"
            print(f"  {emoji} [{insight['type'].upper()}] {insight['content']}")
        
        print("\n" + "="*80 + "\n")
