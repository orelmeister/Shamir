r"""
reconcile_ibkr.py  -  SkyClaw READ-ONLY IBKR account + position puller / DB diff.

Connects to a RUNNING IB Gateway / TWS in READ-ONLY mode (cannot place orders),
prints account balances (incl. cash-vs-margin), lists live positions, and diffs
them against what trading_history.db thinks is open. NEVER trades.

Run AFTER you launch IB Gateway/TWS and log in (2FA). Then:
    .\.venv-weekly\Scripts\python.exe skyclaw_monday_prep\reconcile_ibkr.py
"""
import os, sqlite3, sys
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(REPO, "databases", "trading_history.db")

def env(k, d=None):
    p = os.path.join(REPO, ".env")
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8", errors="ignore"):
            if ln.strip().startswith(k):
                return ln.split("=",1)[1].strip().strip('"').strip("'")
    return os.getenv(k, d)

HOST = env("IB_HOST", "127.0.0.1")
PORTS = [int(env("IB_PORT", "4001")), 7496, 4002, 7497]  # try configured first, then common
CLIENT_ID = 77  # distinct from strategy(10)/exit(11)/weekly(1)

try:
    from ib_insync import IB
except Exception as e:
    print("ib_insync not available in this interpreter:", e)
    print("Use:  .\\.venv-weekly\\Scripts\\python.exe skyclaw_monday_prep\\reconcile_ibkr.py")
    sys.exit(1)

ib = IB()
connected = False
for port in PORTS:
    try:
        ib.connect(HOST, port, clientId=CLIENT_ID, timeout=12, readonly=True)
        print(f"[OK] Connected READ-ONLY to {HOST}:{port} (clientId {CLIENT_ID})")
        connected = True
        break
    except Exception as e:
        print(f"   port {port}: {type(e).__name__} ({e})")

if not connected:
    print("\n[BLOCKED] No IB Gateway/TWS is running/reachable.")
    print("  1) Launch IB Gateway (or TWS) and log in with your 2FA.")
    print("  2) In its API settings enable 'ActiveX and Socket Clients' (port 4001 GW / 7496 TWS).")
    print("  3) Re-run this script and I'll pull balances + positions.")
    sys.exit(2)

# ---- account values ----
want = ["AccountType","NetLiquidation","TotalCashValue","SettledCash","ExcessLiquidity",
        "AvailableFunds","BuyingPower","GrossPositionValue","Cushion","MaintMarginReq"]
vals = {}
for v in ib.accountValues():
    if v.tag in want and v.currency in ("USD",""):
        vals[v.tag] = v.value
print("\n=== ACCOUNT ===")
acct_type = vals.get("AccountType","?")
print(f"  AccountType      : {acct_type}")
for t in want[1:]:
    if t in vals:
        try: print(f"  {t:16}: ${float(vals[t]):,.2f}")
        except: print(f"  {t:16}: {vals[t]}")
# cash vs margin heuristic
is_margin = ("MARGIN" in acct_type.upper()) or (float(vals.get("BuyingPower","0") or 0) > float(vals.get("TotalCashValue","0") or 0)*1.2)
print(f"  -> Looks like a {'MARGIN' if is_margin else 'CASH'} account "
      f"({'same-day capital reuse OK' if is_margin else 'T+1 settlement applies; consider margin upgrade'})")

# ---- live positions ----
print("\n=== LIVE POSITIONS (IBKR) ===")
live = {}
for p in ib.positions():
    sym = p.contract.symbol
    live[sym] = {"qty": p.position, "avgCost": round(p.avgCost,4)}
    print(f"  {sym:6} qty {p.position:>8}  avgCost ${p.avgCost:,.4f}")
if not live:
    print("  (none)")

# ---- DB open positions ----
db_open = {}
if os.path.exists(DB):
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    for r in con.execute("SELECT symbol,quantity,entry_price,agent_name FROM active_positions WHERE status='OPEN'"):
        db_open[r["symbol"]] = {"qty": r["quantity"], "entry": r["entry_price"], "agent": r["agent_name"]}
    con.close()

print("\n=== DIFF (DB active_positions vs IBKR live) ===")
allsyms = sorted(set(live) | set(db_open))
if not allsyms: print("  nothing to compare")
for s in allsyms:
    l = live.get(s); d = db_open.get(s)
    if l and d:
        tag = "MATCH" if abs((l['qty'] or 0)-(d['qty'] or 0))<1e-6 else f"QTY MISMATCH (db {d['qty']} vs live {l['qty']})"
        print(f"  {s:6} {tag}")
    elif l and not d:
        print(f"  {s:6} IN IBKR, NOT IN DB  (untracked live position — qty {l['qty']})")
    else:
        print(f"  {s:6} IN DB, NOT IN IBKR  (stale/closed — db thinks open qty {d['qty']}, agent {d['agent']})")

ib.disconnect()
print("\nRead-only pull complete. No orders were placed. Paste this to SkyClaw for hold/close calls.")
