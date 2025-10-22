"""
Self-Evaluation System for Autonomous Day Trading Bot
Uses LLM to analyze performance and suggest improvements
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import statistics

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_deepseek import ChatDeepSeek
from observability import get_database

logger = logging.getLogger(__name__)


class PerformanceAnalyzer:
    """Analyzes trading performance and generates insights"""
    
    def __init__(self, agent_name: str = "VWAPMomentumAgent"):
        self.agent_name = agent_name
        self.db = get_database()
        
        # Initialize LLM for insights (optional - will fail gracefully if API key missing)
        try:
            self.llm = ChatDeepSeek(
                model="deepseek-chat",
                temperature=0.1  # Low temperature for analytical tasks
            )
            self.llm_available = True
        except Exception as e:
            logger.warning(f"DeepSeek LLM not available: {e}. LLM insights will be skipped.")
            self.llm = None
            self.llm_available = False
    
    def analyze_daily_performance(self, date: Optional[str] = None) -> Dict[str, Any]:
        """Analyze performance for a specific day"""
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Get trades for the day
        trades = self.db.get_trades_by_date(date, self.agent_name)
        
        if not trades:
            return {
                "date": date,
                "status": "no_trades",
                "message": "No trades executed on this day"
            }
        
        # Calculate metrics
        metrics = self._calculate_metrics(trades)
        
        # Get existing daily metrics if any
        existing_metrics = self.db.get_daily_metrics(date, self.agent_name)
        
        # Save/update daily metrics
        self.db.log_daily_metrics({
            **metrics,
            "date": date,
            "agent_name": self.agent_name
        })
        
        return metrics
    
    def _calculate_metrics(self, trades: List[Dict]) -> Dict[str, Any]:
        """Calculate performance metrics from trades"""
        total_trades = len(trades)
        buy_trades = [t for t in trades if t['action'] == 'BUY']
        sell_trades = [t for t in trades if t['action'] == 'SELL']
        
        # Calculate P&L
        profits = [t['profit_loss'] for t in trades if t.get('profit_loss') is not None]
        winning_trades = [p for p in profits if p > 0]
        losing_trades = [p for p in profits if p < 0]
        
        total_profit_loss = sum(profits) if profits else 0.0
        
        # Calculate percentages
        profit_pcts = [t['profit_loss_pct'] for t in trades if t.get('profit_loss_pct') is not None]
        total_profit_loss_pct = sum(profit_pcts) if profit_pcts else 0.0
        
        # Win rate
        win_rate = len(winning_trades) / len(profits) if profits else 0.0
        
        # Average metrics
        avg_win = statistics.mean(winning_trades) if winning_trades else 0.0
        avg_loss = statistics.mean(losing_trades) if losing_trades else 0.0
        
        # Risk/reward ratio
        risk_reward = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0
        
        # Trade duration (if we have entry and exit times)
        durations = []
        position_map = {}
        for trade in trades:
            symbol = trade['symbol']
            if trade['action'] == 'BUY':
                position_map[symbol] = datetime.fromisoformat(trade['timestamp'])
            elif trade['action'] == 'SELL' and symbol in position_map:
                entry_time = position_map[symbol]
                exit_time = datetime.fromisoformat(trade['timestamp'])
                duration = (exit_time - entry_time).total_seconds() / 60  # minutes
                durations.append(duration)
                del position_map[symbol]
        
        avg_duration = statistics.mean(durations) if durations else None
        
        # Capital tracking
        capital_values = [t['capital_at_trade'] for t in trades if t.get('capital_at_trade')]
        capital_start = capital_values[0] if capital_values else None
        capital_end = capital_values[-1] if capital_values else None
        
        # Max drawdown (simplified)
        if profit_pcts:
            cumulative_returns = []
            cumsum = 0
            for pct in profit_pcts:
                cumsum += pct
                cumulative_returns.append(cumsum)
            
            peak = cumulative_returns[0]
            max_dd = 0
            for ret in cumulative_returns:
                if ret > peak:
                    peak = ret
                dd = peak - ret
                if dd > max_dd:
                    max_dd = dd
        else:
            max_dd = 0.0
        
        # Positions held at EOD
        positions_eod = len(position_map)
        
        return {
            "total_trades": total_trades,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "total_profit_loss": total_profit_loss,
            "total_profit_loss_pct": total_profit_loss_pct,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "risk_reward_ratio": risk_reward,
            "max_drawdown": max_dd,
            "avg_trade_duration_minutes": avg_duration,
            "capital_start": capital_start,
            "capital_end": capital_end,
            "positions_held_eod": positions_eod,
            "errors_count": 0  # Will be tracked separately
        }
    
    def generate_llm_insights(self, date: Optional[str] = None) -> Dict[str, Any]:
        """Use LLM to generate insights and recommendations"""
        if not self.llm_available:
            return {
                "date": date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "status": "llm_unavailable",
                "message": "DeepSeek API key not configured. Set DEEPSEEK_API_KEY in .env file."
            }
        
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Get daily metrics
        metrics = self.db.get_daily_metrics(date, self.agent_name)
        
        if not metrics:
            return {
                "date": date,
                "status": "no_data",
                "message": "No metrics available for analysis"
            }
        
        # Get trades for context
        trades = self.db.get_trades_by_date(date, self.agent_name)
        
        # Get historical context (last 7 days)
        start_date = (datetime.fromisoformat(date) - timedelta(days=7)).strftime("%Y-%m-%d")
        historical_metrics = self.db.get_metrics_range(start_date, date, self.agent_name)
        
        # Prepare prompt
        system_prompt = """You are an expert quantitative trading analyst specializing in day trading strategies.
Your role is to analyze trading performance data and provide actionable insights to improve profitability.

Focus on:
1. Pattern recognition in winning vs losing trades
2. Risk management effectiveness
3. Parameter optimization opportunities
4. Market regime adaptation
5. Specific, measurable recommendations

Be concise and data-driven. Provide specific numbers and thresholds in your recommendations."""
        
        analysis_prompt = f"""Analyze the following day trading performance:

DATE: {date}
AGENT: {self.agent_name}

TODAY'S PERFORMANCE:
- Total Trades: {metrics['total_trades']}
- Win Rate: {metrics.get('win_rate', 0) * 100:.1f}%
- Winning Trades: {metrics['winning_trades']}
- Losing Trades: {metrics['losing_trades']}
- Total P&L: ${metrics['total_profit_loss']:.2f} ({metrics['total_profit_loss_pct']:.2f}%)
- Average Win: ${metrics.get('avg_win', 0):.2f}
- Average Loss: ${metrics.get('avg_loss', 0):.2f}
- Risk/Reward Ratio: {metrics.get('risk_reward_ratio', 0):.2f}
- Max Drawdown: {metrics['max_drawdown']:.2f}%
- Avg Trade Duration: {metrics.get('avg_trade_duration_minutes', 0):.1f} minutes
- Positions Held EOD: {metrics['positions_held_eod']}

RECENT TRADES (Sample):
{json.dumps(trades[:5], indent=2) if len(trades) > 0 else "No trades"}

7-DAY TREND:
{self._format_historical_trends(historical_metrics)}

CURRENT STRATEGY PARAMETERS:
- Entry: Price > VWAP, 40 < RSI < 60, ATR > 1.5%
- Profit Target: +1.4%
- Stop Loss: -0.8%
- EOD Liquidation: Enabled

Please provide:
1. **Performance Assessment**: Overall evaluation of today's trading (1-2 sentences)
2. **Key Insights**: What patterns emerge from the data? (3-5 bullet points)
3. **Risk Analysis**: Are we over-trading, under-trading, or managing risk well?
4. **Parameter Recommendations**: Should we adjust any thresholds? Provide specific values.
5. **Action Items**: Top 3 specific improvements for tomorrow

Format as JSON with keys: assessment, insights (array), risk_analysis, parameter_recommendations (array of objects with parameter/current/suggested/reason fields), action_items (array)"""
        
        try:
            # Call LLM
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=analysis_prompt)
            ]
            
            response = self.llm.invoke(messages)
            
            # Parse response (assuming JSON format)
            try:
                insights = json.loads(response.content)
            except json.JSONDecodeError:
                # If not JSON, return raw content
                insights = {
                    "assessment": response.content[:500],
                    "insights": ["See full analysis in raw content"],
                    "raw_content": response.content
                }
            
            # Log evaluation to database
            self.db.log_evaluation({
                "date_range_start": date,
                "date_range_end": date,
                "agent_name": self.agent_name,
                "evaluation_type": "daily_llm_analysis",
                "score": metrics.get('total_profit_loss_pct', 0),
                "insights": json.dumps(insights.get('insights', [])),
                "recommendations": json.dumps(insights.get('parameter_recommendations', [])),
                "metadata": {
                    "metrics": metrics,
                    "full_analysis": insights
                }
            })
            
            return {
                "date": date,
                "status": "success",
                "metrics": metrics,
                "llm_insights": insights
            }
            
        except Exception as e:
            logger.error(f"Error generating LLM insights: {e}")
            return {
                "date": date,
                "status": "error",
                "message": str(e),
                "metrics": metrics
            }
    
    def _format_historical_trends(self, metrics_list: List[Dict]) -> str:
        """Format historical metrics for LLM prompt"""
        if not metrics_list:
            return "No historical data available"
        
        lines = []
        for m in metrics_list[-7:]:  # Last 7 days
            lines.append(
                f"{m['date']}: {m['total_trades']} trades, "
                f"{m['winning_trades']}/{m['losing_trades']} W/L, "
                f"P&L: ${m['total_profit_loss']:.2f} ({m['total_profit_loss_pct']:.2f}%)"
            )
        
        return "\n".join(lines)
    
    def get_parameter_suggestions(self) -> List[Dict[str, Any]]:
        """Get AI-generated parameter optimization suggestions"""
        # Get last 30 days of data
        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        
        metrics_range = self.db.get_metrics_range(start_date, end_date, self.agent_name)
        
        if not metrics_range:
            return []
        
        # Calculate aggregate statistics
        total_trades = sum(m['total_trades'] for m in metrics_range)
        total_wins = sum(m['winning_trades'] for m in metrics_range)
        total_losses = sum(m['losing_trades'] for m in metrics_range)
        total_pnl = sum(m['total_profit_loss'] for m in metrics_range)
        
        win_rate = total_wins / (total_wins + total_losses) if (total_wins + total_losses) > 0 else 0
        
        # Simple heuristics for parameter adjustments
        suggestions = []
        
        # If win rate is low, tighten entry criteria
        if win_rate < 0.45:
            suggestions.append({
                "parameter": "rsi_lower_bound",
                "current_value": 40,
                "suggested_value": 45,
                "reason": f"Win rate is {win_rate*100:.1f}%, tightening RSI range may improve trade quality",
                "priority": "high"
            })
        
        # If win rate is high but P&L is low, widen profit targets
        if win_rate > 0.55 and total_pnl < 0:
            suggestions.append({
                "parameter": "profit_target_pct",
                "current_value": 1.4,
                "suggested_value": 1.6,
                "reason": f"High win rate ({win_rate*100:.1f}%) but negative P&L suggests we're cutting winners too early",
                "priority": "medium"
            })
        
        # If too many positions held EOD, tighten entry or increase monitoring
        avg_eod_positions = statistics.mean([m['positions_held_eod'] for m in metrics_range])
        if avg_eod_positions > 3:
            suggestions.append({
                "parameter": "atr_threshold_pct",
                "current_value": 1.5,
                "suggested_value": 2.0,
                "reason": f"Average {avg_eod_positions:.1f} positions held EOD, higher ATR threshold may reduce overtrading",
                "priority": "medium"
            })
        
        return suggestions


class SelfHealingMonitor:
    """Monitors agent health and performs self-healing actions"""
    
    def __init__(self, agent_name: str = "VWAPMomentumAgent"):
        self.agent_name = agent_name
        self.db = get_database()
    
    def check_health(self, agent_instance: Any) -> Dict[str, Any]:
        """Perform comprehensive health check"""
        try:
            import psutil
            import os
        except ImportError:
            logger.warning("psutil not installed. Install with: pip install psutil")
            return {
                "status": "unknown",
                "cpu_percent": 0.0,
                "memory_mb": 0.0,
                "ibkr_connected": False,
                "issues": ["psutil not available for system monitoring"]
            }
        
        health_status = "healthy"
        issues = []
        
        # Check process resources
        process = psutil.Process(os.getpid())
        cpu_percent = process.cpu_percent(interval=1)
        memory_mb = process.memory_info().rss / 1024 / 1024
        
        if cpu_percent > 80:
            health_status = "degraded"
            issues.append(f"High CPU usage: {cpu_percent:.1f}%")
        
        if memory_mb > 1024:  # >1GB
            health_status = "degraded"
            issues.append(f"High memory usage: {memory_mb:.1f}MB")
        
        # Check IBKR connection
        ibkr_connected = False
        try:
            if hasattr(agent_instance, 'ib'):
                ibkr_connected = agent_instance.ib.isConnected()
                if not ibkr_connected:
                    health_status = "critical"
                    issues.append("IBKR connection lost")
        except Exception as e:
            health_status = "critical"
            issues.append(f"IBKR check failed: {str(e)}")
        
        # Check for recent errors (placeholder)
        last_error = None
        
        # Log health check
        health_data = {
            "agent_name": self.agent_name,
            "health_status": health_status,
            "cpu_percent": cpu_percent,
            "memory_mb": memory_mb,
            "ibkr_connected": 1 if ibkr_connected else 0,
            "last_error": last_error,
            "metadata": {"issues": issues}
        }
        
        self.db.log_health_check(health_data)
        
        return {
            "status": health_status,
            "cpu_percent": cpu_percent,
            "memory_mb": memory_mb,
            "ibkr_connected": ibkr_connected,
            "issues": issues
        }
    
    def attempt_healing(self, agent_instance: Any, issue_type: str) -> bool:
        """Attempt to heal specific issues"""
        logger.info(f"Attempting to heal issue: {issue_type}")
        
        if issue_type == "ibkr_disconnected":
            try:
                # Attempt reconnection
                if hasattr(agent_instance, 'ib'):
                    agent_instance.ib.disconnect()
                    agent_instance.ib.connect('127.0.0.1', 4001, clientId=2)
                    logger.info("Successfully reconnected to IBKR")
                    return True
            except Exception as e:
                logger.error(f"Failed to reconnect to IBKR: {e}")
                return False
        
        return False
