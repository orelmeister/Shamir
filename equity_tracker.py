"""Daily NetLiq snapshots + external cash flows in databases/trading_history.db.

Written by skyclaw_monday_prep/daily_monitor.py (read-only IBKR clientId 77).
Feeds risk_metrics (Sortino/Sharpe/max drawdown on true portfolio returns).

NOTE: trading_performance.db is a dead pipeline (0 rows, 2026-10-04 audit);
trading_history.db is the live database, so these tables live there.

CLI (record a deposit/withdrawal so it doesn't poison the return series):
    python equity_tracker.py add-flow 2026-10-06 500 "deposit"
    python equity_tracker.py add-flow 2026-10-06 -250 "withdrawal"
    python equity_tracker.py show
"""
import os
import sqlite3
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(_HERE, "databases", "trading_history.db")

# NetLiq day-over-day jump (abs %) that triggers a possible-unrecorded-flow flag.
FLOW_SUSPECT_PCT = 0.20


def _connect(db_path=None):
    conn = sqlite3.connect(db_path or DEFAULT_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS equity_snapshots (
            date TEXT PRIMARY KEY,
            net_liq REAL NOT NULL,
            settled_cash REAL,
            source TEXT DEFAULT 'ibkr_clientid77',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cash_flows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
    conn.commit()
    return conn


def record_snapshot(net_liq, settled_cash=None, date=None, db_path=None,
                    source="ibkr_clientid77"):
    """Upsert today's NetLiq snapshot. Returns (date, prior_snapshot_or_None).

    prior snapshot is the most recent snapshot BEFORE `date` — callers use it
    for the unrecorded-flow guard.
    """
    date = date or datetime.now().strftime("%Y-%m-%d")
    conn = _connect(db_path)
    try:
        prior = conn.execute(
            "SELECT date, net_liq FROM equity_snapshots WHERE date < ? "
            "ORDER BY date DESC LIMIT 1", (date,)).fetchone()
        conn.execute(
            "INSERT OR REPLACE INTO equity_snapshots (date, net_liq, settled_cash, source) "
            "VALUES (?, ?, ?, ?)", (date, float(net_liq), settled_cash, source))
        conn.commit()
        return date, prior
    finally:
        conn.close()


def add_cash_flow(date, amount, note="", db_path=None):
    conn = _connect(db_path)
    try:
        conn.execute("INSERT INTO cash_flows (date, amount, note) VALUES (?, ?, ?)",
                     (date, float(amount), note))
        conn.commit()
    finally:
        conn.close()


def get_snapshots(db_path=None):
    """Chronological [(date, net_liq)]."""
    conn = _connect(db_path)
    try:
        return conn.execute(
            "SELECT date, net_liq FROM equity_snapshots ORDER BY date").fetchall()
    finally:
        conn.close()


def get_flows(db_path=None):
    """{date: net_flow} summed per day."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT date, SUM(amount) FROM cash_flows GROUP BY date").fetchall()
        return {d: a for d, a in rows}
    finally:
        conn.close()


def get_trade_returns(db_path=None):
    """Chronological [(iso_date, decimal_return)] from closed trades (SELL rows).

    Source: trading_history.db `trades` table, profit_loss_pct (percent units).
    """
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT timestamp, profit_loss_pct FROM trades "
            "WHERE action = 'SELL' AND profit_loss_pct IS NOT NULL "
            "AND profit_loss_pct != 0 ORDER BY timestamp").fetchall()
        return [(ts[:10], pct / 100.0) for ts, pct in rows]
    finally:
        conn.close()


def flow_suspect(prior, current_net_liq, date, flows=None, db_path=None):
    """True if NetLiq jumped > FLOW_SUSPECT_PCT vs prior snapshot with no
    recorded cash flow on `date` — likely an unrecorded deposit/withdrawal."""
    if not prior or prior[1] <= 0:
        return False
    if flows is None:
        flows = get_flows(db_path)
    if date in flows:
        return False
    return abs(current_net_liq / prior[1] - 1.0) > FLOW_SUSPECT_PCT


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if args and args[0] == "add-flow" and len(args) >= 3:
        d, amt = args[1], float(args[2])
        note = args[3] if len(args) > 3 else ""
        add_cash_flow(d, amt, note)
        print(f"Recorded cash flow {amt:+.2f} on {d} ({note or 'no note'})")
    elif args and args[0] == "show":
        snaps = get_snapshots()
        flows = get_flows()
        print(f"{len(snaps)} snapshots:")
        for d, nl in snaps[-30:]:
            f = flows.get(d)
            print(f"  {d}  ${nl:,.2f}" + (f"  (flow {f:+.2f})" if f else ""))
        if flows:
            print("flows:", flows)
    else:
        print(__doc__)
