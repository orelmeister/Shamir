"""Risk-adjusted performance metrics — pure functions, stdlib only.

Sortino / Sharpe / max drawdown / time-weighted equity returns.
No DB, no IBKR, no network imports — fully unit-testable offline.

Conventions (see docs/SORTINO_RATIO_SPEC.md):
- Returns are decimals (0.012 == +1.2%).
- MAR (minimum acceptable return) defaults to 0 per period (cash-only account).
- Downside deviation uses the full-window denominator (standard Sortino-Frank
  form): DD = sqrt( mean( min(r - MAR, 0)^2 ) ) over ALL N observations.
- Population statistics (ddof=0) throughout, for consistency.
- Insufficient data or zero denominator -> None (rendered "n/a"), never inf,
  never a capped fake number, never an exception for the caller.
- Equity-based daily ratios annualize with sqrt(252). Per-trade ratios are NOT
  annualized (hold periods vary); they are reported raw.
"""
import math

TRADING_DAYS_PER_YEAR = 252
DEFAULT_MIN_OBS = 5
_EPS = 1e-12  # below this, a deviation is floating-point residue, not signal


def _mean(xs):
    return sum(xs) / len(xs)


def _pop_std(xs):
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


def downside_deviation(returns, mar=0.0):
    """Full-window downside deviation vs MAR. None on empty input."""
    if not returns:
        return None
    return math.sqrt(sum(min(r - mar, 0.0) ** 2 for r in returns) / len(returns))


def sortino(returns, mar=0.0, annualization=None, min_obs=DEFAULT_MIN_OBS):
    """Sortino ratio: (mean(r) - MAR) / downside_deviation.

    annualization: periods/year (e.g. 252 for daily returns) or None for raw.
    Returns None when N < min_obs or there is no downside (DD == 0).
    """
    if not returns or len(returns) < min_obs:
        return None
    dd = downside_deviation(returns, mar)
    if dd is None or dd <= _EPS:  # no downside -> undefined, not inf
        return None
    ratio = (_mean(returns) - mar) / dd
    if annualization:
        ratio *= math.sqrt(annualization)
    return ratio


def sharpe(returns, mar=0.0, annualization=None, min_obs=DEFAULT_MIN_OBS):
    """Sharpe ratio: (mean(r) - MAR) / population std. None if N < min_obs or std == 0."""
    if not returns or len(returns) < min_obs:
        return None
    sd = _pop_std(returns)
    if sd <= _EPS:  # constant series (incl. float residue) -> undefined
        return None
    ratio = (_mean(returns) - mar) / sd
    if annualization:
        ratio *= math.sqrt(annualization)
    return ratio


def max_drawdown(equity_curve):
    """Max peak-to-trough drawdown of an equity series, as a NEGATIVE decimal.

    equity_curve: list of equity values (chronological). Returns None if < 2
    points, 0.0 if the curve never declines.
    """
    if not equity_curve or len(equity_curve) < 2:
        return None
    peak = equity_curve[0]
    worst = 0.0
    for v in equity_curve[1:]:
        if v > peak:
            peak = v
        elif peak > 0:
            dd = (v - peak) / peak
            if dd < worst:
                worst = dd
    return worst


def equity_returns(snapshots, flows=None):
    """Time-weighted daily returns from (date, net_liq) snapshots.

    snapshots: chronological list of (date_str, net_liq) tuples.
    flows: optional dict {date_str: net_external_flow} (deposit +, withdrawal -).
           Flow on day d is assumed to arrive BEFORE the day-d snapshot:
           r_d = (NL_d - flow_d) / NL_{d-1} - 1
    Returns list of (date_str, return) for each consecutive pair.
    """
    flows = flows or {}
    out = []
    for (d_prev, nl_prev), (d_cur, nl_cur) in zip(snapshots, snapshots[1:]):
        if nl_prev <= 0:
            continue
        adj = nl_cur - flows.get(d_cur, 0.0)
        out.append((d_cur, adj / nl_prev - 1.0))
    return out


def tail_window(dated_returns, days):
    """Last `days` calendar days of (date, value) pairs, by ISO date string.

    Dates sort lexicographically in ISO form; window is measured from the most
    recent date present, inclusive. Sparse series (trading days only) are fine:
    this means "observations within the trailing `days`-day calendar window".
    """
    if not dated_returns:
        return []
    from datetime import date, timedelta
    last = max(d[:10] for d, _ in dated_returns)
    y, m, dd = (int(x) for x in last.split("-"))
    cutoff = (date(y, m, dd) - timedelta(days=days)).isoformat()
    return [r for d, r in dated_returns if d[:10] > cutoff]


def ratio_summary(dated_returns, windows=(90,), mar=0.0, annualization=None,
                  min_obs=DEFAULT_MIN_OBS):
    """Sortino/Sharpe over each trailing window plus all-time.

    dated_returns: list of (iso_date_str, return).
    Returns dict like {"sortino_90d": x|None, "sharpe_90d": ..., "sortino_all": ...,
                       "sharpe_all": ..., "n_all": N, "n_90d": n}.
    """
    out = {}
    all_r = [r for _, r in dated_returns]
    out["n_all"] = len(all_r)
    out["sortino_all"] = sortino(all_r, mar, annualization, min_obs)
    out["sharpe_all"] = sharpe(all_r, mar, annualization, min_obs)
    for w in windows:
        rs = tail_window(dated_returns, w)
        out[f"n_{w}d"] = len(rs)
        out[f"sortino_{w}d"] = sortino(rs, mar, annualization, min_obs)
        out[f"sharpe_{w}d"] = sharpe(rs, mar, annualization, min_obs)
    return out


def fmt(value, decimals=2):
    """Render a ratio for reports: 'n/a' for None."""
    return "n/a" if value is None else f"{value:.{decimals}f}"
