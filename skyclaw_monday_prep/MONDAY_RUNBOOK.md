# MONDAY RUNBOOK — 2026-08-31 open
_Prepared by SkyClaw, Sun 2026-08-30. Branch: `skyclaw/monday-prep`. Nothing here trades automatically._

**Guiding rule:** the bot has been dark since Feb 9 2026. Monday = **reconcile + observe**, NOT live-trade. No new principal until a real 30/90-day realized record earns it (see `GAME_PLAN_2026-08-30.html`).

---

## STEP 1 — Launch IB Gateway & let SkyClaw read your account (5 min)
SkyClaw cannot log in for you (IBKR needs your 2FA). You do this part:
1. Open **IB Gateway** (or TWS) → log in (live), approve 2FA on IBKR Mobile.
2. Configure → API → Settings: enable **"ActiveX and Socket Clients"**, port **4001** (GW) / 7496 (TWS), trusted IP `127.0.0.1`.
3. Tell SkyClaw "Gateway is up" — or run it yourself:
   ```powershell
   cd C:\Users\orelm\OneDrive\Documents\GitHub\trade
   .\.venv-weekly\Scripts\python.exe skyclaw_monday_prep\reconcile_ibkr.py
   ```
   This is **read-only** (`readonly=True`) — it cannot place orders. It prints your balance,
   whether you're **cash vs margin**, your **live positions**, and a **diff vs the database**.
4. Paste the output to SkyClaw → you get a **hold/close call on each stale Feb position**.

## STEP 2 — Review the fresh candidate watchlist (already generated)
- File: `skyclaw_monday_prep\output\monday_watchlist_*.json` (regenerate anytime):
  ```powershell
  .\.venv-weekly\Scripts\python.exe skyclaw_monday_prep\monday_scan.py
  ```
- Read-only signal scan (Senate/House + Form 4 open-market purchases, last 100d, politician-first).
- `**` = politician **and** insider-cluster (strongest). Does **not** place orders.

## STEP 3 — Cash-only discipline (NO margin, ever — David's rule)
- **This account never uses margin, leverage, or borrowing.** Trade only the cash that's actually there.
- That's fine: the swing strategy holds days-to-weeks, so it never needs same-day capital reuse.
  Sell -> let the cash settle (T+1) -> redeploy the next day. Only ever deploy **settled** cash; keep a small buffer; don't churn.
- If the account is technically a margin account, we simply never use the margin — settled cash only.

## STEP 4 — Paper / dry-run the Form 4 strategy (NO live orders)
- The strategy already supports saving orders to JSON instead of executing. Run the analysis pass,
  review what it *would* buy, and log it. Do **not** pass any auto-execute flag.
- Goal this week: build a **real, realized** track record — every position must eventually be
  closed (round-trip), not left open.

## STEP 5 — If (and only if) you choose to trade live
- Max 5–6 positions, equal weight, **−8% hard stop** each, no adds.
- Account kill-switch: halt new entries at **−15% from peak equity**.
- Benchmark weekly vs just holding SPY. If not beating SPY after costs, the edge isn't there.

---

## Housekeeping done for you (on branch `skyclaw/monday-prep`)
- `reconcile_ibkr.py` — read-only account/position puller + DB diff.
- `monday_scan.py` — live politician/insider purchase watchlist.
- `monte_carlo_real.py` — a REAL risk simulation (replaces the fake `monte_carlo_filter.py`).
- `fix_data_bug.py` — repairs the −100% manual-close mislog that corrupted analytics.
- DB backed up to `databases\trading_history.backup_*.db` before any change.

## Decisions SkyClaw still needs from you
1. Actual IBKR balance (cash-only is a given — **never margin**).
2. Green-light the pivot: retire intraday day-trader, focus Form 4 swing, paper-first?
3. Cash-only is locked in as a permanent rule — no margin, no leverage, ever.
4. The stale Feb positions — hold or close each (after Step 1 diff)?
