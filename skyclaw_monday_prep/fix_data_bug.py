"""
fix_data_bug.py  -  Repair the -100% manual-close mislog that corrupts analytics.

The exit manager logged manually-closed positions (HPP, DAWN) as profit_loss_pct = -100
with reason MANUAL_CLOSE_DETECTED. They did NOT lose 100%; the true P&L is unknown.
This sets those profit_loss_pct values to NULL (unknown) so they stop poisoning every
win-rate / expectancy / Monte-Carlo calculation, and annotates the reason. Backs up first.

Run:  python skyclaw_monday_prep\fix_data_bug.py          (dry-run, shows what it would do)
      python skyclaw_monday_prep\fix_data_bug.py --apply  (writes the fix)
"""
import sqlite3, os, sys, shutil
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(REPO, "databases", "trading_history.db")
APPLY = "--apply" in sys.argv

con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
bad = con.execute("SELECT id,symbol,profit_loss_pct,exit_reason FROM closed_positions_today "
                  "WHERE profit_loss_pct <= -99.9").fetchall()
print(f"Found {len(bad)} corrupt -100% rows:")
for r in bad:
    print(f"   id={r['id']} {r['symbol']} {r['profit_loss_pct']}% ({r['exit_reason']})")

if not bad:
    print("Nothing to fix."); con.close(); sys.exit(0)

if not APPLY:
    print("\nDRY-RUN. Re-run with --apply to write:  set profit_loss_pct=NULL, "
          "append ' [corrected: mislog, true P&L unknown]' to exit_reason.")
    con.close(); sys.exit(0)

bak = os.path.join(REPO, "databases", f"trading_history.prefix_{datetime.now():%Y%m%d_%H%M%S}.db")
shutil.copy2(DB, bak); print(f"\nBackup: {os.path.basename(bak)}")
cur = con.cursor()
for r in bad:
    cur.execute("UPDATE closed_positions_today SET profit_loss_pct=NULL, "
                "exit_reason = exit_reason || ' [corrected: mislog, true P&L unknown]' WHERE id=?", (r["id"],))
con.commit()
print(f"Applied fix to {len(bad)} rows. Analytics will no longer be poisoned by fake -100% losses.")
con.close()
