"""
Database Setup for Form 4 Monitoring Agent
Creates form4_positions table in trading_history.db
"""

import sqlite3
from pathlib import Path

DATABASE_PATH = Path("trading_history.db")

def setup_database():
    """Create form4_positions table"""
    
    print("\n" + "="*80)
    print("DATABASE SETUP - Form 4 Monitoring Agent")
    print("="*80 + "\n")
    
    if not DATABASE_PATH.exists():
        print(f"[!] Creating new database: {DATABASE_PATH}")
    else:
        print(f"[+] Using existing database: {DATABASE_PATH}")
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Enable WAL mode for concurrent access
    cursor.execute("PRAGMA journal_mode=WAL")
    
    # Create form4_positions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS form4_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            entry_date DATE NOT NULL,
            entry_price REAL NOT NULL,
            shares INTEGER NOT NULL,
            hold_period_days INTEGER NOT NULL,
            current_price REAL,
            days_held INTEGER,
            unrealized_pnl REAL,
            status TEXT DEFAULT 'ACTIVE',
            llm_reasoning TEXT,
            last_check_date DATE,
            exit_date DATE,
            exit_price REAL,
            exit_reason TEXT,
            analysis_confidence REAL,
            analysis_bull_case TEXT,
            analysis_bear_case TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create indexes for performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_form4_positions_symbol 
        ON form4_positions(symbol)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_form4_positions_status 
        ON form4_positions(status)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_form4_positions_entry_date 
        ON form4_positions(entry_date)
    """)
    
    conn.commit()
    
    # Verify table exists
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='form4_positions'
    """)
    
    if cursor.fetchone():
        print("✅ Table created: form4_positions")
        
        # Show table structure
        cursor.execute("PRAGMA table_info(form4_positions)")
        columns = cursor.fetchall()
        
        print("\n[SCHEMA] form4_positions:")
        for col in columns:
            col_id, name, col_type, not_null, default, pk = col
            nullable = "NOT NULL" if not_null else "NULL"
            pk_str = " [PRIMARY KEY]" if pk else ""
            default_str = f" DEFAULT {default}" if default else ""
            print(f"  {name}: {col_type} {nullable}{default_str}{pk_str}")
        
        # Check indexes
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND tbl_name='form4_positions'
        """)
        indexes = cursor.fetchall()
        
        print("\n[INDEXES]:")
        for idx in indexes:
            print(f"  - {idx[0]}")
        
        # Count existing positions
        cursor.execute("SELECT COUNT(*) FROM form4_positions WHERE status='ACTIVE'")
        active_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM form4_positions WHERE status='CLOSED'")
        closed_count = cursor.fetchone()[0]
        
        print(f"\n[POSITIONS]:")
        print(f"  Active: {active_count}")
        print(f"  Closed: {closed_count}")
        print(f"  Total: {active_count + closed_count}")
    else:
        print("❌ Failed to create table")
    
    conn.close()
    
    print("\n" + "="*80)
    print("DATABASE SETUP COMPLETE")
    print("="*80 + "\n")


def insert_test_position():
    """Insert a test position for agent testing"""
    
    print("\n" + "="*80)
    print("INSERTING TEST POSITION")
    print("="*80 + "\n")
    
    from datetime import datetime, timedelta
    
    # Test position: AAPL bought 7 days ago
    test_position = {
        'symbol': 'AAPL',
        'entry_date': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
        'entry_price': 225.50,
        'shares': 10,
        'hold_period_days': 14,
        'status': 'ACTIVE',
        'analysis_confidence': 85.0,
        'analysis_bull_case': 'Strong director buying cluster, positive earnings catalyst',
        'analysis_bear_case': 'High valuation, sector rotation risk'
    }
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO form4_positions 
        (symbol, entry_date, entry_price, shares, hold_period_days, status,
         analysis_confidence, analysis_bull_case, analysis_bear_case)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        test_position['symbol'],
        test_position['entry_date'],
        test_position['entry_price'],
        test_position['shares'],
        test_position['hold_period_days'],
        test_position['status'],
        test_position['analysis_confidence'],
        test_position['analysis_bull_case'],
        test_position['analysis_bear_case']
    ))
    
    conn.commit()
    position_id = cursor.lastrowid
    conn.close()
    
    print(f"✅ Test position inserted (ID: {position_id}):")
    print(f"   Symbol: {test_position['symbol']}")
    print(f"   Entry: {test_position['entry_date']} @ ${test_position['entry_price']}")
    print(f"   Shares: {test_position['shares']}")
    print(f"   Hold Period: {test_position['hold_period_days']} days")
    print(f"   Status: {test_position['status']}")
    
    print("\n[NEXT STEP] Test the monitoring agent:")
    print("  & .\\.venv-daytrader\\Scripts\\python.exe weekly_bot\\form4_monitor_agent.py")
    
    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    import sys
    
    setup_database()
    
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        insert_test_position()
