"""
Observability Infrastructure for Autonomous Day Trading Bot
Uses OpenTelemetry for tracing and SQLite for trade storage
"""

import sqlite3
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from contextlib import contextmanager
import logging
from pathlib import Path

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

logger = logging.getLogger(__name__)

class TradingDatabase:
    """SQLite database for storing all trading operations and metrics"""
    
    def __init__(self, db_path: str = "trading_history.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize database schema"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Trades table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price REAL NOT NULL,
                    agent_name TEXT NOT NULL,
                    reason TEXT,
                    profit_loss REAL,
                    profit_loss_pct REAL,
                    capital_at_trade REAL,
                    position_size_pct REAL,
                    metadata TEXT
                )
            """)
            
            # Daily metrics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL UNIQUE,
                    total_trades INTEGER DEFAULT 0,
                    winning_trades INTEGER DEFAULT 0,
                    losing_trades INTEGER DEFAULT 0,
                    total_profit_loss REAL DEFAULT 0,
                    total_profit_loss_pct REAL DEFAULT 0,
                    max_drawdown REAL DEFAULT 0,
                    sharpe_ratio REAL,
                    avg_trade_duration_minutes REAL,
                    capital_start REAL,
                    capital_end REAL,
                    positions_held_eod INTEGER DEFAULT 0,
                    errors_count INTEGER DEFAULT 0,
                    agent_name TEXT NOT NULL,
                    metadata TEXT
                )
            """)
            
            # Agent health table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agent_health (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    health_status TEXT NOT NULL,
                    cpu_percent REAL,
                    memory_mb REAL,
                    ibkr_connected INTEGER,
                    last_error TEXT,
                    metadata TEXT
                )
            """)
            
            # Parameter changes table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS parameter_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    parameter_name TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT NOT NULL,
                    reason TEXT,
                    approved_by TEXT,
                    metadata TEXT
                )
            """)
            
            # Performance evaluation table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    date_range_start TEXT NOT NULL,
                    date_range_end TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    evaluation_type TEXT NOT NULL,
                    score REAL,
                    insights TEXT,
                    recommendations TEXT,
                    metadata TEXT
                )
            """)
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def log_trade(self, trade_data: Dict[str, Any]) -> int:
        """Log a trade to the database"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trades (
                    timestamp, symbol, action, quantity, price, agent_name,
                    reason, profit_loss, profit_loss_pct, capital_at_trade,
                    position_size_pct, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_data.get('timestamp', datetime.now(timezone.utc).isoformat()),
                trade_data['symbol'],
                trade_data['action'],
                trade_data['quantity'],
                trade_data['price'],
                trade_data['agent_name'],
                trade_data.get('reason'),
                trade_data.get('profit_loss'),
                trade_data.get('profit_loss_pct'),
                trade_data.get('capital_at_trade'),
                trade_data.get('position_size_pct'),
                json.dumps(trade_data.get('metadata', {}))
            ))
            conn.commit()
            return cursor.lastrowid
    
    def log_daily_metrics(self, metrics: Dict[str, Any]) -> int:
        """Log daily performance metrics"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO daily_metrics (
                    date, total_trades, winning_trades, losing_trades,
                    total_profit_loss, total_profit_loss_pct, max_drawdown,
                    sharpe_ratio, avg_trade_duration_minutes, capital_start,
                    capital_end, positions_held_eod, errors_count, agent_name, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metrics['date'],
                metrics.get('total_trades', 0),
                metrics.get('winning_trades', 0),
                metrics.get('losing_trades', 0),
                metrics.get('total_profit_loss', 0.0),
                metrics.get('total_profit_loss_pct', 0.0),
                metrics.get('max_drawdown', 0.0),
                metrics.get('sharpe_ratio'),
                metrics.get('avg_trade_duration_minutes'),
                metrics.get('capital_start'),
                metrics.get('capital_end'),
                metrics.get('positions_held_eod', 0),
                metrics.get('errors_count', 0),
                metrics['agent_name'],
                json.dumps(metrics.get('metadata', {}))
            ))
            conn.commit()
            return cursor.lastrowid
    
    def log_health_check(self, health_data: Dict[str, Any]) -> int:
        """Log agent health status"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agent_health (
                    timestamp, agent_name, health_status, cpu_percent,
                    memory_mb, ibkr_connected, last_error, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                health_data.get('timestamp', datetime.now(timezone.utc).isoformat()),
                health_data['agent_name'],
                health_data['health_status'],
                health_data.get('cpu_percent'),
                health_data.get('memory_mb'),
                health_data.get('ibkr_connected', 0),
                health_data.get('last_error'),
                json.dumps(health_data.get('metadata', {}))
            ))
            conn.commit()
            return cursor.lastrowid
    
    def log_parameter_change(self, change_data: Dict[str, Any]) -> int:
        """Log parameter changes"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO parameter_changes (
                    timestamp, agent_name, parameter_name, old_value,
                    new_value, reason, approved_by, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                change_data.get('timestamp', datetime.now(timezone.utc).isoformat()),
                change_data['agent_name'],
                change_data['parameter_name'],
                change_data.get('old_value'),
                change_data['new_value'],
                change_data.get('reason'),
                change_data.get('approved_by', 'AUTO'),
                json.dumps(change_data.get('metadata', {}))
            ))
            conn.commit()
            return cursor.lastrowid
    
    def log_evaluation(self, eval_data: Dict[str, Any]) -> int:
        """Log performance evaluation"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO evaluations (
                    timestamp, date_range_start, date_range_end, agent_name,
                    evaluation_type, score, insights, recommendations, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                eval_data.get('timestamp', datetime.now(timezone.utc).isoformat()),
                eval_data['date_range_start'],
                eval_data['date_range_end'],
                eval_data['agent_name'],
                eval_data['evaluation_type'],
                eval_data.get('score'),
                eval_data.get('insights'),
                eval_data.get('recommendations'),
                json.dumps(eval_data.get('metadata', {}))
            ))
            conn.commit()
            return cursor.lastrowid
    
    def get_trades_by_date(self, date: str, agent_name: Optional[str] = None) -> List[Dict]:
        """Get all trades for a specific date"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if agent_name:
                cursor.execute("""
                    SELECT * FROM trades 
                    WHERE DATE(timestamp) = ? AND agent_name = ?
                    ORDER BY timestamp
                """, (date, agent_name))
            else:
                cursor.execute("""
                    SELECT * FROM trades 
                    WHERE DATE(timestamp) = ?
                    ORDER BY timestamp
                """, (date,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_recent_trades(self, limit: int = 100, agent_name: Optional[str] = None) -> List[Dict]:
        """Get recent trades"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if agent_name:
                cursor.execute("""
                    SELECT * FROM trades 
                    WHERE agent_name = ?
                    ORDER BY timestamp DESC LIMIT ?
                """, (agent_name, limit))
            else:
                cursor.execute("""
                    SELECT * FROM trades 
                    ORDER BY timestamp DESC LIMIT ?
                """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_daily_metrics(self, date: str, agent_name: Optional[str] = None) -> Optional[Dict]:
        """Get daily metrics for a specific date"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if agent_name:
                cursor.execute("""
                    SELECT * FROM daily_metrics 
                    WHERE date = ? AND agent_name = ?
                """, (date, agent_name))
            else:
                cursor.execute("""
                    SELECT * FROM daily_metrics 
                    WHERE date = ?
                """, (date,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_metrics_range(self, start_date: str, end_date: str, agent_name: Optional[str] = None) -> List[Dict]:
        """Get daily metrics for a date range"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if agent_name:
                cursor.execute("""
                    SELECT * FROM daily_metrics 
                    WHERE date BETWEEN ? AND ? AND agent_name = ?
                    ORDER BY date
                """, (start_date, end_date, agent_name))
            else:
                cursor.execute("""
                    SELECT * FROM daily_metrics 
                    WHERE date BETWEEN ? AND ?
                    ORDER BY date
                """, (start_date, end_date))
            return [dict(row) for row in cursor.fetchall()]


class TradingTracer:
    """OpenTelemetry tracing for trading operations"""
    
    def __init__(self, service_name: str = "autonomous-day-trader"):
        # Create resource
        resource = Resource.create({
            "service.name": service_name,
            "service.version": "1.0.0"
        })
        
        # Set up tracer provider
        provider = TracerProvider(resource=resource)
        
        # Add console exporter for local development
        console_exporter = ConsoleSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(console_exporter))
        
        # Set as global tracer provider
        trace.set_tracer_provider(provider)
        
        # Get tracer
        self.tracer = trace.get_tracer(__name__)
        
        logger.info(f"OpenTelemetry tracing initialized for {service_name}")
    
    def trace_trade_execution(self, symbol: str, action: str):
        """Create a span for trade execution"""
        return self.tracer.start_as_current_span(
            f"trade.{action}",
            attributes={
                "trade.symbol": symbol,
                "trade.action": action
            }
        )
    
    def trace_analysis(self, symbol: str, analysis_type: str):
        """Create a span for market analysis"""
        return self.tracer.start_as_current_span(
            f"analysis.{analysis_type}",
            attributes={
                "analysis.symbol": symbol,
                "analysis.type": analysis_type
            }
        )
    
    def trace_health_check(self, agent_name: str):
        """Create a span for health check"""
        return self.tracer.start_as_current_span(
            "health.check",
            attributes={
                "agent.name": agent_name
            }
        )


# Global instances
_db_instance = None
_tracer_instance = None

def get_database() -> TradingDatabase:
    """Get or create global database instance"""
    global _db_instance
    if _db_instance is None:
        _db_instance = TradingDatabase()
    return _db_instance

def get_tracer() -> TradingTracer:
    """Get or create global tracer instance"""
    global _tracer_instance
    if _tracer_instance is None:
        _tracer_instance = TradingTracer()
    return _tracer_instance
