"""
monte_carlo_real.py  -  A REAL Monte Carlo risk simulation for the Form 4 swing strategy.

Replaces the misnamed monte_carlo_filter.py (which is just a confidence sort).
Bootstraps the empirical distribution of the bot's own CLOSED-trade returns
(from trading_history.db), excluding the corrupt -100% manual-close artifacts,
and simulates a year of trading across many paths. Reports median/percentile
outcomes, probability of a down year, and drawdown. READ-ONLY on the DB.
"""
import sqlite3, statistics, random, os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(REPO, "databases", "trading_history.db")

def load_returns():
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    rows = con.execute("SELECT symbol,profit_loss_pct,exit_reason FROM closed_positions_today "
                       "WHERE profit_loss_pct IS NOT NULL").fetchall()
    con.close()
    clean, artifacts = [], []
    for r in rows:
        x = float(r["profit_loss_pct"]) / 100.0
        (artifacts if x <= -0.99 else clean).append((r["symbol"], x, r["exit_reason"]))
    return clean, artifacts

def stats(sample):
    w = [x for x in sample if x > 0]; l = [x for x in sample if x <= 0]
    return {"n":len(sample), "win":len(w)/len(sample), "avg":statistics.mean(sample),
            "avg_win":statistics.mean(w) if w else 0, "avg_loss":statistics.mean(l) if l else 0}

def montecarlo(sample, trades_per_year=48, concurrent=6, paths=20000, bear=0.0, seed=7):
    random.seed(seed)
    f = 1.0/concurrent
    ends, dds = [], []
    for _ in range(paths):
        cap = peak = 1.0; dd = 0.0
        for _ in range(trades_per_year):
            if bear > 0 and random.random() < bear:
                r = max(random.gauss(-0.06, 0.05), -0.20)   # bear-regime stop-out
            else:
                r = random.choice(sample)
            cap *= (1 + f*r); peak = max(peak, cap); dd = max(dd, (peak-cap)/peak)
        ends.append(cap); dds.append(dd)
    ends.sort()
    p = lambda q: ends[int(q*len(ends))]
    return {"median":statistics.median(ends), "p5":p(0.05), "p25":p(0.25), "p75":p(0.75),
            "p95":p(0.95), "p_loss":sum(1 for e in ends if e<1)/len(ends),
            "dd_med":statistics.median(dds), "dd_worst5":sorted(dds)[int(0.95*len(dds))]}

if __name__ == "__main__":
    clean, artifacts = load_returns()
    if artifacts:
        print("Excluded corrupt artifacts (manual-close mislog):",
              [(s, f"{x*100:.0f}%") for s,x,_ in artifacts])
    print("Clean closed-trade returns (n=%d):" % len(clean), sorted(round(x*100,1) for _,x,_ in clean))
    s = stats([x for _,x,_ in clean])
    print(f"\nWin rate {s['win']*100:.0f}% | avg {s['avg']*100:+.2f}%/trade | "
          f"avgWin {s['avg_win']*100:+.2f}% | avgLoss {s['avg_loss']*100:+.2f}% | "
          f"payoff {abs(s['avg_win']/s['avg_loss']):.2f}")
    sample = [x for _,x,_ in clean]
    print("\n%-34s %8s %7s %7s %8s %9s" % ("SCENARIO","median/yr","P(down)","maxDD","5th","95th"))
    for label, bear in [("as-is (bull tailwind)",0.0), ("realistic (20% bear stop-outs)",0.20),
                        ("conservative (35% bear)",0.35)]:
        m = montecarlo(sample, bear=bear)
        print("%-34s %+7.0f%% %7.0f%% %6.0f%% %+7.0f%% %+8.0f%%" % (
            label, (m["median"]-1)*100, m["p_loss"]*100, m["dd_worst5"]*100,
            (m["p5"]-1)*100, (m["p95"]-1)*100))
    print("\nNOTE: sample is small (n=%d) and drawn from a rising market. Illustrative, not predictive." % len(clean))
