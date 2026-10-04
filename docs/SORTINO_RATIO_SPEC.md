# Sortino Ratio & Risk-Adjusted Metrics — Spec v2 (AS BUILT)

**Status:** Implemented 2026-10-04 · **Author:** SkyClaw · **Approved:** David ("Yes. And build it")
**v1 → v2 changes (per review):** equity snapshots promoted to first priority; daily-$PnL Sortino **deleted**; per-trade ratios use 90d/all-time windows (not 30d); max drawdown added; proper cash-flow (TWR) guard added; LLM-prompt integration **deferred** until ≥90 observations; everything is observational — zero governor/gate impact.

---

## 1. Definitions

- Returns are decimals. **MAR = 0** per period (cash-only account, no benchmark mandate).
- **Downside deviation** (Sortino-Frank, full-window denominator): `DD = sqrt(mean(min(r − MAR, 0)²))` over all N.
- **Sortino** `= (mean(r) − MAR) / DD` · **Sharpe** `= (mean(r) − MAR) / pop_std(r)`.
- Equity daily returns annualize ×√252. **Per-trade returns are NOT annualized** (variable hold periods) — raw ratios.
- **Max drawdown**: worst peak-to-trough % of the NetLiq curve, reported negative.
- Edge cases → `None`, rendered `n/a`: `N < 5` (min_obs), zero/epsilon downside (no losers ≠ infinite skill), constant series (std ≤ 1e-12 — float residue guard, found by test).

## 2. Data reality (audited 2026-10-04)

- `databases/trading_performance.db` is a **dead pipeline — 0 rows in every table**. v1 planned to extend it; v2 ignores it.
- `databases/trading_history.db` is live: `trades` (176 rows; 22 SELLs with `profit_loss_pct`), `daily_metrics`, `closed_positions_today`, etc. All new tables live here.
- No historical daily NetLiq exists anywhere → true portfolio-return ratios begin accruing from first monitor run after this ships.

## 3. Components (as built)

### `risk_metrics.py` (repo root) — pure functions, stdlib only
`downside_deviation`, `sortino`, `sharpe`, `max_drawdown`, `equity_returns` (TWR with flow adjustment), `tail_window`, `ratio_summary`, `fmt`. No DB/IBKR/network imports.

### `equity_tracker.py` (repo root) — persistence in `trading_history.db`
- Tables (CREATE IF NOT EXISTS, no migration risk):
  - `equity_snapshots(date PK, net_liq, settled_cash, source, created_at)`
  - `cash_flows(id, date, amount, note, created_at)`
- `record_snapshot()` — daily upsert; returns prior snapshot for the flow guard.
- `get_trade_returns()` — `trades` SELL rows with non-null/non-zero `profit_loss_pct` → `[(date, decimal)]`.
- `flow_suspect()` — NetLiq jump >20% vs prior snapshot with no recorded flow that day.
- CLI: `python equity_tracker.py add-flow YYYY-MM-DD <amount> "note"` · `python equity_tracker.py show`.
- Flow convention: flow on day d arrives before day-d snapshot → `r_d = (NL_d − flow_d) / NL_{d−1} − 1`.

### `skyclaw_monday_prep/daily_monitor.py` — three additions, all wrapped in try/except so metrics can never break the safety report
1. After the ACCOUNT line: `record_snapshot(NetLiq, SettledCash)`.
2. `FLAG:` line if `flow_suspect()` — tells David the exact `add-flow` command to run.
3. Before disconnect, a `RISK-ADJUSTED` block:
   - Per-trade Sortino 90d + all-time, Sharpe all-time (raw, MAR 0%), with n counts.
   - Once **≥20 snapshots** accrue: equity-based annualized Sortino/Sharpe 90d + max drawdown. Until then: `accruing snapshots (N/20)`.

## 4. Out of scope / deferred

- **No governor, entry-gate, sizing, or PROPOSE→AUTO changes.** Any ratio-driven gate is a CONSTITUTION amendment requiring David's explicit approval.
- LLM insight prompts do NOT receive the ratios until ≥90 observations (noise narration is worse than silence).
- NetLiq backfill from IBKR Flex statements — possible future work.
- `trading_performance.db` revival — separate decision; not part of this.

## 5. Verification (done 2026-10-04)

- `python tests/test_risk_metrics.py` — **20/20 pass** (unittest, stdlib; temp DBs; no pytest dependency — none of the four venvs has it). Covers: hand-computed known-answer series (Sortino 0.3 / Sharpe 0.174371), annualization, all-positive → Sortino None while Sharpe computes, N<min_obs, constant-series float-residue guard, max-drawdown curve, TWR flow adjustment, snapshot upsert/prior, flow-suspect guard, real `trades` schema extraction, 25-snapshot end-to-end.
- Real-DB smoke: 22 closed trades → all-time Sortino **−0.11**, Sharpe **−0.09**; 90d `n/a` (n=4 < 5). Matches expectation for a series dominated by the Aug–Sep stop-outs (GS −8.3%, AB −7.9%, IREN −16.1%, OMEX −21.5%).
- `py_compile` clean on all three touched files. Monitor's IBKR path unchanged (read-only clientId 77); full-report run verifies on the next trading day.

## 6. Interpretation guidance (for humans, not gates)

- Per-trade all-time Sortino < 0 = losers outweigh winners on a downside-risk basis. Current −0.11 reflects the known Aug–Sep drawdown cluster; the constitution gates (Laws II/III/VI/VII) that now exist postdate most of that series.
- Treat 90d values as the trend signal once n ≥ 5; all-time as the record. >1.0 good, <0 poor, in-between = keep sample size in mind before concluding anything.
