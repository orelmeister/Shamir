"""
monday_scan.py  -  SkyClaw Monday-prep candidate scanner (READ-ONLY, no IBKR, no orders)

Pulls live congressional (Senate/House) + insider (Form 4) *purchases* from FMP,
applies the repo's politician-first scoring hierarchy, and prints a ranked watchlist
for Monday's open. Costs a handful of FMP calls. Never touches IBKR. Never trades.

Scoring hierarchy (mirrors weekly_bot/05_form4_strategy.py):
  Politician (Senate/House) = 3.0   |  Director = 2.0  |  10% owner = 2.0  |  Officer = 0.2
Filters (mirror strategy constants): lookback 100d, price >= $1, mkt cap >= $100M.
"""
import urllib.request, urllib.parse, json, os, sys
from datetime import datetime, timedelta
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUT, exist_ok=True)
LOOKBACK_DAYS = 100
MIN_PRICE = 1.0
MIN_MKT_CAP = 100_000_000

def load_key():
    p = os.path.join(REPO, ".env")
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8", errors="ignore"):
            if ln.strip().startswith("FMP_API_KEY"):
                return ln.split("=",1)[1].strip().strip('"').strip("'")
    return os.getenv("FMP_API_KEY","")
KEY = load_key()

def get(url):
    u = url + ("&" if "?" in url else "?") + "apikey=" + KEY
    try:
        req = urllib.request.Request(u, headers={"User-Agent":"skyclaw-scan"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"   [warn] fetch failed: {e}")
        return None

def parse_date(s):
    if not s: return None
    s = str(s)[:10]
    try: return datetime.strptime(s, "%Y-%m-%d")
    except: return None

cutoff = datetime.now() - timedelta(days=LOOKBACK_DAYS)

# ---------------- 1) POLITICIAN PURCHASES ----------------
print("=== Fetching congressional purchases (Senate + House, last %dd) ===" % LOOKBACK_DAYS)
pol = defaultdict(lambda: {"count":0, "people":set(), "dates":[], "latest":None})
for ep in ("senate-latest", "house-latest"):
    data = get(f"https://financialmodelingprep.com/stable/{ep}") or []
    kept = 0
    for r in data:
        typ = str(r.get("type","")).lower()
        if "purchase" not in typ: continue
        d = parse_date(r.get("transactionDate"))
        if not d or d < cutoff: continue
        sym = (r.get("symbol") or "").upper().strip()
        if not sym or len(sym) > 5: continue
        who = (str(r.get("firstName","")) + " " + str(r.get("lastName",""))).strip() or r.get("office","")
        p = pol[sym]; p["count"] += 1; p["people"].add(who); p["dates"].append(d)
        p["latest"] = max(p["latest"], d) if p["latest"] else d
        kept += 1
    print(f"   {ep}: {len(data)} rows, {kept} qualifying purchases")

# ---------------- 2) INSIDER (FORM 4) OPEN-MARKET PURCHASES ----------------
print("\n=== Fetching insider open-market purchases (Form 4 P-Purchase) ===")
ins = defaultdict(lambda: {"buyers":set(), "count":0, "dir":0, "off":0, "own":0, "value":0.0, "latest":None})
def classify(role):
    r = (role or "").lower()
    if "director" in r or "board" in r: return "dir"
    if "10%" in r or "ten percent" in r: return "own"
    if any(w in r for w in ["officer","ceo","cfo","coo","president","chief","vp","exec"]): return "off"
    return "off"
got = 0
for page in range(0, 12):
    data = get(f"https://financialmodelingprep.com/api/v4/insider-trading?transactionType=P-Purchase&page={page}")
    if not data: break
    stop = False
    for r in data:
        d = parse_date(r.get("transactionDate"))
        if not d: continue
        if d < cutoff: stop = True; continue
        sym = (r.get("symbol") or "").upper().strip()
        if not sym: continue
        who = r.get("reportingName","?")
        role = r.get("typeOfOwner","")
        it = ins[sym]; it["buyers"].add(who); it["count"] += 1
        it[classify(role)] += 1
        try: it["value"] += float(r.get("securitiesTransacted") or 0) * float(r.get("price") or 0)
        except: pass
        it["latest"] = max(it["latest"], d) if it["latest"] else d
        got += 1
    if stop and page >= 1: break
print(f"   collected {got} insider purchase records across {len(ins)} symbols")

# ---------------- 3) BUILD RANKED CANDIDATES ----------------
symbols = set(pol) | {s for s,v in ins.items() if len(v["buyers"]) >= 2 or s in pol}
rows = []
for s in symbols:
    pc = pol[s]["count"] if s in pol else 0
    ppl = len(pol[s]["people"]) if s in pol else 0
    ib = len(ins[s]["buyers"]) if s in ins else 0
    d  = ins[s]["dir"] if s in ins else 0
    o  = ins[s]["off"] if s in ins else 0
    latest = max([x for x in [pol[s]["latest"] if s in pol else None, ins[s]["latest"] if s in ins else None] if x], default=None)
    # weighted quality (politician-first): politician dominates, insider cluster adds
    score = 0.0
    if pc: score += 3.0 + 0.25*min(ppl-1,4)
    score += min(2.0, 2.0*(1 if d else 0)) * (1 if d else 0)  # director present -> up to 2.0
    score += 0.2*o
    score += 0.15*max(ib-1,0)                                   # cluster bonus
    tier = "A (politician)" if pc else ("B (insider cluster)" if ib>=2 else "C")
    star = "**" if (pc and ib>=2) else ("*" if pc else "")
    rows.append({"symbol":s,"tier":tier,"score":round(score,3),"politician_buys":pc,"politicians":ppl,
                 "insider_buyers":ib,"directors":d,"officers":o,
                 "latest": latest.strftime("%Y-%m-%d") if latest else "",
                 "days_ago": (datetime.now()-latest).days if latest else None, "flag":star})

rows.sort(key=lambda x:(x["tier"][0], -x["score"], -(x["politician_buys"]), -(x["insider_buyers"])))

# ---------------- 4) ENRICH TOP WITH QUOTE (price/mktcap filter) ----------------
top = [r for r in rows if r["tier"].startswith(("A","B"))][:20]
if top:
    q = get("https://financialmodelingprep.com/api/v3/quote/" + ",".join(r["symbol"] for r in top)) or []
    qm = {x.get("symbol"):x for x in q}
    for r in top:
        x = qm.get(r["symbol"], {})
        r["price"] = x.get("price")
        r["mktcap"] = x.get("marketCap")
        r["name"] = x.get("name","")
        r["passes_filter"] = bool(x.get("price") and x["price"]>=MIN_PRICE and (x.get("marketCap") or 0)>=MIN_MKT_CAP)

# ---------------- 5) REPORT ----------------
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
print("\n" + "="*78)
print("MONDAY CANDIDATE WATCHLIST  (politician-first, last %dd)  %s" % (LOOKBACK_DAYS, ts))
print("="*78)
print("** = politician + insider cluster (strongest)   * = politician-backed\n")
hdr = f"{'SYM':6} {'TIER':16} {'SCORE':6} {'POLbuys':7} {'INSbuy':6} {'DIR':4} {'AGE':4} {'PRICE':>8} {'MKTCAP':>10}  NAME"
print(hdr); print("-"*len(hdr))
for r in top:
    mc = r.get("mktcap") or 0
    mcs = (f"${mc/1e9:.1f}B" if mc>=1e9 else f"${mc/1e6:.0f}M") if mc else "-"
    pr = f"${r['price']:.2f}" if r.get("price") else "-"
    fl = "" if r.get("passes_filter", True) else "  <micro/penny-skip>"
    print(f"{r['symbol']:6} {r['tier']:16} {r['score']:<6} {r['politician_buys']:^7} {r['insider_buyers']:^6} {r['directors']:^4} {str(r.get('days_ago','')):^4} {pr:>8} {mcs:>10}  {r.get('name','')[:24]}{r['flag']}{fl}")

json.dump({"generated":ts,"lookback_days":LOOKBACK_DAYS,"candidates":rows,"top":top},
          open(os.path.join(OUT, f"monday_watchlist_{ts}.json"),"w"), indent=2, default=str)
print(f"\nSaved: skyclaw_monday_prep/output/monday_watchlist_{ts}.json")
print("NOTE: read-only signal scan. No IBKR connection, no orders. LLM conviction debate NOT run (do that Monday).")
