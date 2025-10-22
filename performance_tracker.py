"""
Performance Tracking and Monitoring System
Stores trade history and performance metrics in SQLite database
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

class PerformanceTracker:
    """Tracks and stores trading performance in SQLite database"""
    
    def __init__(self, db_path="trading_performance.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Daily performance summary table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_performance (
                date TEXT PRIMARY KEY,
                total_trades INTEGER DEFAULT 0,
                profitable_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0.0,
                win_rate REAL DEFAULT 0.0,
                avg_profit REAL DEFAULT 0.0,
                avg_loss REAL DEFAULT 0.0,
                avg_hold_time_seconds INTEGER DEFAULT 0,
                best_trade_ticker TEXT,
                best_trade_pnl REAL,
                worst_trade_ticker TEXT,
                worst_trade_pnl REAL,
                stocks_analyzed INTEGER DEFAULT 0,
                watchlist_size INTEGER DEFAULT 0,
                parameters JSON,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Individual trades table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                ticker TEXT NOT NULL,
                action TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                total_value REAL NOT NULL,
                pnl REAL DEFAULT 0.0,
                pnl_percent REAL DEFAULT 0.0,
                hold_time_seconds INTEGER DEFAULT 0,
                entry_time TEXT,
                exit_time TEXT,
                entry_price REAL,
                exit_price REAL,
                indicators JSON,
                exit_reason TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Market conditions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_conditions (
                date TEXT PRIMARY KEY,
                market_regime TEXT,
                avg_volatility REAL,
                total_volume BIGINT,
                market_sentiment TEXT,
                vix_level REAL,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Parameter adjustments history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS parameter_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                parameter_name TEXT NOT NULL,
                old_value REAL,
                new_value REAL,
                reason TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Performance insights from LLM
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                insight_type TEXT NOT NULL,
                content TEXT NOT NULL,
                actionable BOOLEAN DEFAULT 0,
                implemented BOOLEAN DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    def log_trade(self, trade_data):
        """Log an individual trade"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO trades (
                date, timestamp, ticker, action, quantity, price, 
                total_value, pnl, pnl_percent, hold_time_seconds,
                entry_time, exit_time, entry_price, exit_price,
                indicators, exit_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_data.get('date', datetime.now().strftime('%Y-%m-%d')),
            trade_data.get('timestamp', datetime.now().isoformat()),
            trade_data['ticker'],
            trade_data['action'],
            trade_data['quantity'],
            trade_data['price'],
            trade_data.get('total_value', trade_data['quantity'] * trade_data['price']),
            trade_data.get('pnl', 0.0),
            trade_data.get('pnl_percent', 0.0),
            trade_data.get('hold_time_seconds', 0),
            trade_data.get('entry_time'),
            trade_data.get('exit_time'),
            trade_data.get('entry_price'),
            trade_data.get('exit_price'),
            json.dumps(trade_data.get('indicators', {})),
            trade_data.get('exit_reason')
        ))
        
        conn.commit()
        conn.close()
    
    def update_daily_summary(self, date, summary_data):
        """Update daily performance summary"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO daily_performance (
                date, total_trades, profitable_trades, losing_trades,
                total_pnl, win_rate, avg_profit, avg_loss,
                avg_hold_time_seconds, best_trade_ticker, best_trade_pnl,
                worst_trade_ticker, worst_trade_pnl, stocks_analyzed,
                watchlist_size, parameters
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            date,
            summary_data.get('total_trades', 0),
            summary_data.get('profitable_trades', 0),
            summary_data.get('losing_trades', 0),
            summary_data.get('total_pnl', 0.0),
            summary_data.get('win_rate', 0.0),
            summary_data.get('avg_profit', 0.0),
            summary_data.get('avg_loss', 0.0),
            summary_data.get('avg_hold_time_seconds', 0),
            summary_data.get('best_trade_ticker'),
            summary_data.get('best_trade_pnl'),
            summary_data.get('worst_trade_ticker'),
            summary_data.get('worst_trade_pnl'),
            summary_data.get('stocks_analyzed', 0),
            summary_data.get('watchlist_size', 0),
            json.dumps(summary_data.get('parameters', {}))
        ))
        
        conn.commit()
        conn.close()
    
    def get_daily_summary(self, date):
        """Get daily performance summary"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM daily_performance WHERE date = ?
        """, (date,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        return None
    
    def get_trades_for_date(self, date):
        """Get all trades for a specific date"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM trades WHERE date = ? ORDER BY timestamp
        """, (date,))
        
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        conn.close()
        
        return [dict(zip(columns, row)) for row in rows]
    
    def get_performance_history(self, days=30):
        """Get performance history for last N days"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM daily_performance 
            ORDER BY date DESC 
            LIMIT ?
        """, (days,))
        
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        conn.close()
        
        return [dict(zip(columns, row)) for row in rows]
    
    def log_parameter_change(self, param_name, old_value, new_value, reason):
        """Log parameter adjustment"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO parameter_history (
                date, parameter_name, old_value, new_value, reason
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime('%Y-%m-%d'),
            param_name,
            old_value,
            new_value,
            reason
        ))
        
        conn.commit()
        conn.close()
    
    def log_insight(self, insight_type, content, actionable=False):
        """Log an insight from analysis"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO insights (
                date, insight_type, content, actionable
            ) VALUES (?, ?, ?, ?)
        """, (
            datetime.now().strftime('%Y-%m-%d'),
            insight_type,
            content,
            actionable
        ))
        
        conn.commit()
        conn.close()
    
    def get_statistics(self):
        """Get overall trading statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Overall stats
        cursor.execute("""
            SELECT 
                COUNT(*) as total_trading_days,
                SUM(total_trades) as total_trades,
                SUM(profitable_trades) as total_wins,
                SUM(losing_trades) as total_losses,
                SUM(total_pnl) as cumulative_pnl,
                AVG(win_rate) as avg_win_rate,
                MAX(total_pnl) as best_day_pnl,
                MIN(total_pnl) as worst_day_pnl
            FROM daily_performance
        """)
        
        stats = cursor.fetchone()
        columns = [desc[0] for desc in cursor.description]
        conn.close()
        
        return dict(zip(columns, stats)) if stats else {}
