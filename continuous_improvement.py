"""
Continuous Improvement System for Autonomous Day Trading Bot
Implements adaptive thresholds, market regime detection, and parameter optimization
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import statistics
import numpy as np

from observability import get_database
from self_evaluation import PerformanceAnalyzer

logger = logging.getLogger(__name__)


class MarketRegimeDetector:
    """Detects market conditions and adapts strategy accordingly"""
    
    REGIMES = {
        "trending_up": "Strong upward momentum, favor momentum trades",
        "trending_down": "Strong downward pressure, reduce position sizes",
        "ranging": "Sideways movement, favor mean reversion",
        "high_volatility": "Elevated volatility, widen stops and targets",
        "low_volatility": "Low volatility, tighten entry criteria"
    }
    
    def __init__(self):
        self.current_regime = "ranging"
        self.regime_confidence = 0.0
    
    def detect_regime(self, market_data: Dict[str, Any]) -> str:
        """
        Detect current market regime based on recent data
        
        Args:
            market_data: Dict with keys like 'spy_returns', 'vix', 'volume_ratio', etc.
        
        Returns:
            Regime name from REGIMES dict
        """
        # Simple regime detection based on market metrics
        spy_returns = market_data.get('spy_returns', [])
        vix = market_data.get('vix', 15)
        
        if not spy_returns:
            return "ranging"
        
        # Calculate trend
        avg_return = statistics.mean(spy_returns)
        volatility = statistics.stdev(spy_returns) if len(spy_returns) > 1 else 0
        
        # High volatility regime
        if vix > 25 or volatility > 2.0:
            self.current_regime = "high_volatility"
            self.regime_confidence = min((vix - 15) / 20, 1.0)
        
        # Low volatility regime
        elif vix < 12 and volatility < 0.5:
            self.current_regime = "low_volatility"
            self.regime_confidence = min((12 - vix) / 7, 1.0)
        
        # Trending regimes
        elif avg_return > 0.5:
            self.current_regime = "trending_up"
            self.regime_confidence = min(avg_return / 2, 1.0)
        
        elif avg_return < -0.5:
            self.current_regime = "trending_down"
            self.regime_confidence = min(abs(avg_return) / 2, 1.0)
        
        # Default to ranging
        else:
            self.current_regime = "ranging"
            self.regime_confidence = 0.5
        
        logger.info(f"Market regime detected: {self.current_regime} (confidence: {self.regime_confidence:.2f})")
        return self.current_regime
    
    def get_regime_adjustments(self) -> Dict[str, float]:
        """
        Get parameter adjustments based on current regime
        
        Returns:
            Dict of parameter multipliers
        """
        adjustments = {
            "profit_target_multiplier": 1.0,
            "stop_loss_multiplier": 1.0,
            "position_size_multiplier": 1.0,
            "atr_threshold_multiplier": 1.0,
            "rsi_range_adjustment": 0  # +/- adjustment to RSI bounds
        }
        
        if self.current_regime == "high_volatility":
            # Widen stops and targets, reduce position size
            adjustments["profit_target_multiplier"] = 1.3
            adjustments["stop_loss_multiplier"] = 1.3
            adjustments["position_size_multiplier"] = 0.7
            adjustments["atr_threshold_multiplier"] = 1.2
        
        elif self.current_regime == "low_volatility":
            # Tighten ranges, normal position sizes
            adjustments["profit_target_multiplier"] = 0.9
            adjustments["stop_loss_multiplier"] = 0.9
            adjustments["position_size_multiplier"] = 1.0
            adjustments["atr_threshold_multiplier"] = 0.8
        
        elif self.current_regime == "trending_up":
            # Let winners run, tighter stops
            adjustments["profit_target_multiplier"] = 1.2
            adjustments["stop_loss_multiplier"] = 0.9
            adjustments["position_size_multiplier"] = 1.1
            adjustments["rsi_range_adjustment"] = 5  # 45-65 instead of 40-60
        
        elif self.current_regime == "trending_down":
            # Defensive positioning
            adjustments["position_size_multiplier"] = 0.6
            adjustments["atr_threshold_multiplier"] = 1.3
            adjustments["rsi_range_adjustment"] = -5  # 35-55 instead of 40-60
        
        return adjustments


class AdaptiveThresholdManager:
    """Manages dynamic parameter adjustments based on performance"""
    
    def __init__(self, agent_name: str = "VWAPMomentumAgent"):
        self.agent_name = agent_name
        self.db = get_database()
        self.analyzer = PerformanceAnalyzer(agent_name)
        
        # Current parameters (defaults)
        self.parameters = {
            "profit_target_pct": 1.4,
            "stop_loss_pct": 0.8,
            "rsi_lower_bound": 40,
            "rsi_upper_bound": 60,
            "atr_threshold_pct": 1.5,
            "max_position_size_pct": 5.0
        }
        
        # Parameter bounds (safety limits)
        self.bounds = {
            "profit_target_pct": (0.8, 3.0),
            "stop_loss_pct": (0.5, 2.0),
            "rsi_lower_bound": (30, 50),
            "rsi_upper_bound": (50, 70),
            "atr_threshold_pct": (1.0, 3.0),
            "max_position_size_pct": (3.0, 10.0)
        }
    
    def update_parameters(self, suggestions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Update parameters based on suggestions
        
        Args:
            suggestions: List of {parameter, current_value, suggested_value, reason}
        
        Returns:
            Dict of changes made
        """
        changes = {}
        
        for suggestion in suggestions:
            param = suggestion['parameter']
            suggested = suggestion['suggested_value']
            
            if param not in self.parameters:
                logger.warning(f"Unknown parameter: {param}")
                continue
            
            # Validate against bounds
            min_val, max_val = self.bounds.get(param, (None, None))
            if min_val is not None and suggested < min_val:
                logger.warning(f"{param} suggestion {suggested} below minimum {min_val}")
                suggested = min_val
            if max_val is not None and suggested > max_val:
                logger.warning(f"{param} suggestion {suggested} above maximum {max_val}")
                suggested = max_val
            
            # Apply change
            old_value = self.parameters[param]
            self.parameters[param] = suggested
            
            # Log change
            self.db.log_parameter_change({
                "agent_name": self.agent_name,
                "parameter_name": param,
                "old_value": str(old_value),
                "new_value": str(suggested),
                "reason": suggestion.get('reason', 'AI-suggested optimization'),
                "approved_by": "AUTO"
            })
            
            changes[param] = {
                "old": old_value,
                "new": suggested,
                "reason": suggestion.get('reason')
            }
            
            logger.info(f"Updated {param}: {old_value} -> {suggested}")
        
        return changes
    
    def get_current_parameters(self) -> Dict[str, float]:
        """Get current parameter values"""
        return self.parameters.copy()
    
    def apply_regime_adjustments(self, regime_adjustments: Dict[str, float]) -> Dict[str, float]:
        """
        Apply regime-based adjustments to parameters (temporary, not logged)
        
        Returns:
            Adjusted parameters for current trading session
        """
        adjusted = self.parameters.copy()
        
        # Apply multipliers
        adjusted["profit_target_pct"] *= regime_adjustments.get("profit_target_multiplier", 1.0)
        adjusted["stop_loss_pct"] *= regime_adjustments.get("stop_loss_multiplier", 1.0)
        adjusted["atr_threshold_pct"] *= regime_adjustments.get("atr_threshold_multiplier", 1.0)
        adjusted["max_position_size_pct"] *= regime_adjustments.get("position_size_multiplier", 1.0)
        
        # Apply RSI adjustments
        rsi_adj = regime_adjustments.get("rsi_range_adjustment", 0)
        adjusted["rsi_lower_bound"] = max(30, min(50, adjusted["rsi_lower_bound"] + rsi_adj))
        adjusted["rsi_upper_bound"] = max(50, min(70, adjusted["rsi_upper_bound"] + rsi_adj))
        
        # Ensure bounds
        for param, (min_val, max_val) in self.bounds.items():
            if param in adjusted:
                adjusted[param] = max(min_val, min(max_val, adjusted[param]))
        
        return adjusted


class ABTestingFramework:
    """A/B testing framework for strategy variations"""
    
    def __init__(self, agent_name: str = "VWAPMomentumAgent"):
        self.agent_name = agent_name
        self.db = get_database()
        self.active_tests = {}
    
    def create_test(self, test_name: str, variant_a: Dict, variant_b: Dict, duration_days: int = 7) -> str:
        """
        Create a new A/B test
        
        Args:
            test_name: Name of the test
            variant_a: Parameter set for variant A (control)
            variant_b: Parameter set for variant B (test)
            duration_days: How long to run the test
        
        Returns:
            Test ID
        """
        test_id = f"{test_name}_{datetime.now(timezone.utc).strftime('%Y%m%d')}"
        
        self.active_tests[test_id] = {
            "name": test_name,
            "variant_a": variant_a,
            "variant_b": variant_b,
            "start_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=duration_days)).strftime("%Y-%m-%d"),
            "status": "active"
        }
        
        logger.info(f"Created A/B test: {test_id}")
        return test_id
    
    def get_variant(self, test_id: str, date: str) -> Tuple[str, Dict]:
        """
        Get which variant to use for a given date (alternating days)
        
        Returns:
            Tuple of (variant_name, parameters)
        """
        test = self.active_tests.get(test_id)
        if not test:
            return "control", {}
        
        # Alternate by day of month
        day = int(date.split('-')[2])
        if day % 2 == 0:
            return "variant_a", test["variant_a"]
        else:
            return "variant_b", test["variant_b"]
    
    def evaluate_test(self, test_id: str) -> Dict[str, Any]:
        """
        Evaluate A/B test results
        
        Returns:
            Dict with winner, metrics comparison, and statistical significance
        """
        test = self.active_tests.get(test_id)
        if not test:
            return {"error": "Test not found"}
        
        start_date = test["start_date"]
        end_date = test["end_date"]
        
        # Get metrics for both variants
        metrics_range = self.db.get_metrics_range(start_date, end_date, self.agent_name)
        
        variant_a_days = []
        variant_b_days = []
        
        for metrics in metrics_range:
            date = metrics["date"]
            day = int(date.split('-')[2])
            if day % 2 == 0:
                variant_a_days.append(metrics)
            else:
                variant_b_days.append(metrics)
        
        # Calculate aggregate metrics
        def aggregate_metrics(days):
            if not days:
                return {}
            return {
                "total_trades": sum(d["total_trades"] for d in days),
                "winning_trades": sum(d["winning_trades"] for d in days),
                "losing_trades": sum(d["losing_trades"] for d in days),
                "total_pnl": sum(d["total_profit_loss"] for d in days),
                "avg_pnl_per_day": statistics.mean([d["total_profit_loss"] for d in days]),
                "win_rate": sum(d["winning_trades"] for d in days) / sum(d["total_trades"] for d in days) if sum(d["total_trades"] for d in days) > 0 else 0
            }
        
        a_metrics = aggregate_metrics(variant_a_days)
        b_metrics = aggregate_metrics(variant_b_days)
        
        # Determine winner
        winner = "variant_a" if a_metrics.get("total_pnl", 0) > b_metrics.get("total_pnl", 0) else "variant_b"
        
        return {
            "test_id": test_id,
            "test_name": test["name"],
            "variant_a_metrics": a_metrics,
            "variant_b_metrics": b_metrics,
            "winner": winner,
            "improvement_pct": ((b_metrics.get("total_pnl", 0) - a_metrics.get("total_pnl", 0)) / abs(a_metrics.get("total_pnl", 1)) * 100) if a_metrics.get("total_pnl") else 0
        }


class ContinuousImprovementEngine:
    """Main engine coordinating all continuous improvement activities"""
    
    def __init__(self, agent_name: str = "VWAPMomentumAgent"):
        self.agent_name = agent_name
        self.db = get_database()
        self.analyzer = PerformanceAnalyzer(agent_name)
        self.regime_detector = MarketRegimeDetector()
        self.threshold_manager = AdaptiveThresholdManager(agent_name)
        self.ab_testing = ABTestingFramework(agent_name)
    
    def daily_improvement_cycle(self, market_data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Run daily improvement cycle
        
        This should be called at end of trading day to:
        1. Analyze performance
        2. Generate LLM insights
        3. Get parameter suggestions
        4. Update thresholds if appropriate
        5. Detect market regime
        
        Returns:
            Dict with all improvement actions taken
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        logger.info(f"Starting daily improvement cycle for {today}")
        
        # 1. Analyze performance
        performance = self.analyzer.analyze_daily_performance(today)
        
        # 2. Generate LLM insights
        insights = self.analyzer.generate_llm_insights(today)
        
        # 3. Get parameter suggestions
        param_suggestions = self.analyzer.get_parameter_suggestions()
        
        # 4. Update thresholds (only if high confidence suggestions)
        changes = {}
        high_priority_suggestions = [s for s in param_suggestions if s.get('priority') == 'high']
        if high_priority_suggestions:
            changes = self.threshold_manager.update_parameters(high_priority_suggestions)
        
        # 5. Detect market regime
        regime = "ranging"  # Default
        if market_data:
            regime = self.regime_detector.detect_regime(market_data)
        
        # 6. Compile report
        report = {
            "date": today,
            "performance": performance,
            "llm_insights": insights.get("llm_insights"),
            "parameter_suggestions": param_suggestions,
            "parameter_changes": changes,
            "market_regime": regime,
            "regime_confidence": self.regime_detector.regime_confidence,
            "current_parameters": self.threshold_manager.get_current_parameters()
        }
        
        # Save report
        self._save_improvement_report(report)
        
        logger.info(f"Daily improvement cycle complete. Changes made: {len(changes)}")
        
        return report
    
    def get_trading_parameters(self, market_data: Optional[Dict] = None) -> Dict[str, float]:
        """
        Get optimized parameters for current trading session
        
        Combines:
        - Base learned parameters
        - Market regime adjustments
        - Active A/B test variants
        
        Returns:
            Dict of parameters to use for trading
        """
        # Start with base parameters
        params = self.threshold_manager.get_current_parameters()
        
        # Apply regime adjustments if market data available
        if market_data:
            regime = self.regime_detector.detect_regime(market_data)
            regime_adjustments = self.regime_detector.get_regime_adjustments()
            params = self.threshold_manager.apply_regime_adjustments(regime_adjustments)
        
        return params
    
    def _save_improvement_report(self, report: Dict[str, Any]):
        """Save daily improvement report to file"""
        reports_dir = Path("reports/improvement")
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        filename = reports_dir / f"improvement_report_{report['date']}.json"
        with open(filename, 'w') as f:
            json.dump(report, indent=2, fp=f)
        
        logger.info(f"Saved improvement report to {filename}")
