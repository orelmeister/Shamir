"""Daily read-only trading monitor. One shot, deterministic output for the cron agent.

Reports:
  - account cash / net liq
  - SWING sleeve (Form-4 insider-cluster): P&L vs -8% stop + verifies GTC stop orders exist
  - ROBOTICS sleeve (long-horizon): P&L vs -25% REVIEW trigger (NO auto-stop by design)
  - kill-switch: -15% from peak equity (swing sleeve only)
  - M-gate (Law VI): SPX vs 50-day SMA + distribution days (IBKR-sourced, no FMP)

Exit code 0 always (report-only). FLAG lines start with 'FLAG:' for easy grep.
"""
import os, sys
from ib_insync import IB, Stock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))  # trade repo root: risk_metrics / equity_tracker
from market_calendar import market_status
import governor
import risk_metrics as rm
import equity_tracker as eqt

ROBOTICS = governor.ROBOTICS_SYMS
SWING_STOPS = {"DKS": 122.37, "MTDR": 53.86}  # documented -8% levels (09-01 entries)

trading, cal_note = market_status()
if not trading:
    print(f"MARKET CLOSED today: {cal_note}. Positions unchanged; skipping full report.")
    sys.exit(0)
if cal_note:
    print(f"NOTE: {cal_note}")

ib = IB()
ib.connect("127.0.0.1", 4001, clientId=77, timeout=15, readonly=True)

vals = {}
for v in ib.accountValues():
    if v.tag in ("NetLiquidation", "SettledCash", "TotalCashValue") and v.currency in ("USD", ""):
        vals[v.tag] = float(v.value)
print(f"ACCOUNT NetLiq=${vals.get('NetLiquidation',0):,.2f} Settled=${vals.get('SettledCash',0):,.2f}")

# Daily equity snapshot (feeds Sortino/Sharpe/max-drawdown; docs/SORTINO_RATIO_SPEC.md)
try:
    _nl = vals.get("NetLiquidation", 0)
    if _nl > 0:
        _snap_date, _prior = eqt.record_snapshot(_nl, vals.get("SettledCash"))
        if eqt.flow_suspect(_prior, _nl, _snap_date):
            print(f"FLAG: NetLiq moved >20% vs last snapshot (${_prior[1]:,.2f} on {_prior[0]}) "
                  f"with no recorded cash flow — if a deposit/withdrawal happened, run: "
                  f"python equity_tracker.py add-flow {_snap_date} <amount> \"note\"")
except Exception as _e:  # metrics must never break the safety report
    print(f"NOTE: equity snapshot failed ({_e})")

ib.reqMarketDataType(3)
positions = ib.positions()

# open SELL stop orders by symbol
stops_open = {}
for t in ib.reqAllOpenOrders():
    if t.order.orderType.startswith("STP") and t.order.action == "SELL":
        stops_open[t.contract.symbol] = t.order.auxPrice

def px(sym):
    """Last traded price via delayed historical bars (streaming delayed ticks are flaky)."""
    c = Stock(sym, "SMART", "USD")
    try:
        ib.qualifyContracts(c)
        bars = ib.reqHistoricalData(c, endDateTime="", durationStr="1 D",
                                    barSizeSetting="5 mins", whatToShow="TRADES", useRTH=False)
        if bars:
            return bars[-1].close
    except Exception:
        pass
    return None

print("\nPOSITIONS:")
for p in positions:
    sym, qty, cost = p.contract.symbol, p.position, p.avgCost
    sleeve = "ROBOTICS" if sym in ROBOTICS else "SWING"
    last = px(sym)
    if not last:
        print(f"  {sym:6} [{sleeve}] qty {qty:g} cost ${cost:.2f} last=? (no quote)")
        continue
    pnl = (last - cost) / cost * 100
    line = f"  {sym:6} [{sleeve}] qty {qty:g} cost ${cost:.2f} last ${last:.2f} P&L {pnl:+.1f}%"
    if sleeve == "SWING":
        stop = SWING_STOPS.get(sym)
        has_stop = sym in stops_open
        line += f" | stop {'GTC@'+format(stops_open[sym],'.2f') if has_stop else 'MISSING'}"
        print(line)
        if not has_stop:
            print(f"FLAG: {sym} has NO live stop order — re-place GTC stop (replace_swing_stops.py)")
        if stop and last <= stop:
            print(f"FLAG: {sym} at/below -8% stop level ${stop:.2f}")
    else:
        print(line + " | no stop by design (-25% review)")
        if pnl <= -25:
            print(f"FLAG: {sym} breached -25% ROBOTICS REVIEW trigger — needs manual review with David")

# M-gate (Law VI): SPX vs 50-day SMA + distribution days (trailing 2 weeks).
# Self-contained via IBKR (FMP was rate-limiting on 2026-10-05; don't depend on it here).
def _m_gate():
    try:
        c = Stock("SPY", "SMART", "USD")
        ib.qualifyContracts(c)
        bars = ib.reqHistoricalData(c, endDateTime="", durationStr="80 D",
                                    barSizeSetting="1 day", whatToShow="TRADES", useRTH=True)
        if not bars or len(bars) < 55:
            return {"error": "insufficient SPY history"}
        closes = [b.close for b in bars]
        vols = [b.volume for b in bars]
        sma50 = sum(closes[-50:]) / 50.0
        below = closes[-1] < sma50
        dist = 0
        for i in range(len(bars) - 10, len(bars)):
            if i > 0 and closes[i] < closes[i - 1] and vols[i] >= vols[i - 1]:
                dist += 1
        blocked = bool(below or dist >= 2)
        return {"spy_last": round(closes[-1], 2), "sma50": round(sma50, 2),
                "below_50d": bool(below), "distribution_days": dist, "blocked": blocked}
    except Exception as _e:
        return {"error": str(_e)}

_mg = _m_gate()
if "error" in _mg:
    print(f"\nM-GATE: unavailable ({_mg['error']})")
else:
    state = "BLOCKED (no new entries)" if _mg["blocked"] else "OPEN"
    print(f"\nM-GATE: SPY ${_mg['spy_last']} vs 50d ${_mg['sma50']} | below50d={_mg['below_50d']} | dist_days={_mg['distribution_days']} | {state}")
    if _mg["blocked"]:
        print("FLAG: M-gate BLOCKED — no new entries (SPX < 50-day or 2+ distribution days)")

# risk governor (Law III): swing equity vs peak
swing_val = sum(p.position * p.avgCost for p in positions if p.contract.symbol not in ROBOTICS)
eq = governor.swing_equity(vals.get("SettledCash", 0), swing_val)
g = governor.get_tier(eq)
print(f"\nGOVERNOR: {g['tier']} | swing equity ${eq:,.0f} | peak ${g['peak']:,.0f} | dd {g['drawdown_pct']}% | robotics reserved ${governor.robotics_reserved():,.0f}")
if g["tier"] == "REDUCED":
    print("FLAG: governor REDUCED — half-size new entries only")
elif g["tier"] == "CRITICAL":
    print("FLAG: governor CRITICAL (-15% kill-switch) — NO new entries, exits only")

# Risk-adjusted performance (observational only — no gate/governor effect)
try:
    trade_rets = eqt.get_trade_returns()
    ts = rm.ratio_summary(trade_rets, windows=(90,))  # per-trade: NOT annualized
    snaps = eqt.get_snapshots()
    line = (f"\nRISK-ADJUSTED (MAR 0%): per-trade Sortino 90d {rm.fmt(ts['sortino_90d'])} "
            f"(n={ts['n_90d']}) | all-time {rm.fmt(ts['sortino_all'])} (n={ts['n_all']}) "
            f"| Sharpe all-time {rm.fmt(ts['sharpe_all'])}")
    if len(snaps) >= 20:
        eq_rets = rm.equity_returns(snaps, eqt.get_flows())
        es = rm.ratio_summary(eq_rets, windows=(90,),
                              annualization=rm.TRADING_DAYS_PER_YEAR)
        mdd = rm.max_drawdown([nl for _, nl in snaps])
        line += (f"\n  equity (daily, annualized): Sortino 90d {rm.fmt(es['sortino_90d'])} "
                 f"| Sharpe 90d {rm.fmt(es['sharpe_90d'])} "
                 f"| max drawdown {rm.fmt(mdd * 100 if mdd is not None else None, 1)}%")
    else:
        line += f"\n  equity-based ratios: accruing snapshots ({len(snaps)}/20)"
    print(line)
except Exception as _e:
    print(f"NOTE: risk metrics failed ({_e})")

ib.disconnect()
print("\nDone (read-only, no orders placed).")
