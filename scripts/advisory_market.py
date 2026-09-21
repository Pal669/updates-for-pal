"""Investment Advisory Universe: the numbers (markets, sectors, rates, commodities, REITs/InvITs) -> data/advisory_market.json.

Python standard library only, no API keys, no AI. Run once a day after the market close:
    python scripts/advisory_market.py

Sources (every block on the page names its own):
  NSE index feed (nseindia.com/api/allIndices)  index levels, 1D / 1W / 1M / 1Y, index P/E, advances and declines
  NSE FII/DII feed (api/fiidiiTradeReact)       daily institutional cash-market flows
  Yahoo Finance chart endpoint                  global indices, US yields, dollar, gold, silver, crude, USD/INR,
                                                REIT / InvIT prices (BSE tickers: the NSE tickers on Yahoo are stale)
  RBI homepage                                  policy repo rate, SDF, MSF, bank rate, CRR, SLR (official)
  TradingView symbol page                       India 10-year G-Sec yield (best effort; dropped if it cannot be read)

Nothing here is estimated or rewritten. A block that cannot be fetched is simply left out and the page says so.
If NSE blocks the request (cloud servers are sometimes blocked) the main indices fall back to Yahoo, with 1D only for
the sector indices.
"""
import html, json, re, sys, time, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "advisory_market.json"
IST = timezone(timedelta(hours=5, minutes=30))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
      "Accept": "application/json,text/html,*/*", "Accept-Language": "en-US,en;q=0.9"}

INDEX_ROWS = [  # NSE index name, label shown
    ("NIFTY 50", "Nifty 50"), ("NIFTY NEXT 50", "Nifty Next 50"), ("NIFTY 500", "Nifty 500"),
    ("NIFTY MIDCAP 150", "Nifty Midcap 150"), ("NIFTY SMALLCAP 250", "Nifty Smallcap 250"),
    ("NIFTY MIDSMALLCAP 400", "Nifty MidSmallcap 400"), ("NIFTY BANK", "Nifty Bank"),
    ("NIFTY FINANCIAL SERVICES", "Nifty Financial Services"), ("INDIA VIX", "India VIX"),
]
SECTOR_ROWS = [
    ("NIFTY AUTO", "Auto"), ("NIFTY PRIVATE BANK", "Private Banks"), ("NIFTY PSU BANK", "PSU Banks"),
    ("NIFTY FINANCIAL SERVICES", "Financial Services"), ("NIFTY FMCG", "FMCG"), ("NIFTY IT", "IT"),
    ("NIFTY MEDIA", "Media"), ("NIFTY METAL", "Metal"), ("NIFTY PHARMA", "Pharma"),
    ("NIFTY HEALTHCARE INDEX", "Healthcare"), ("NIFTY REALTY", "Realty"), ("NIFTY CONSUMER DURABLES", "Consumer Durables"),
    ("NIFTY OIL & GAS", "Oil & Gas"), ("NIFTY CHEMICALS", "Chemicals"), ("NIFTY CEMENT", "Cement"),
    ("NIFTY REITS & REALTY", "REITs & Realty"),
]
# (label, Yahoo symbol, decimals, group, unit note)
GLOBAL = [("S&P 500", "%5EGSPC", 0), ("Nasdaq Composite", "%5EIXIC", 0), ("FTSE 100", "%5EFTSE", 0), ("DAX", "%5EGDAXI", 0),
          ("Nikkei 225", "%5EN225", 0), ("Hang Seng", "%5EHSI", 0), ("Shanghai Composite", "000001.SS", 0)]
RATES_FX = [("US 10-year yield (%)", "%5ETNX", 3), ("US 5-year yield (%)", "%5EFVX", 3), ("US 13-week bill (%)", "%5EIRX", 3),
            ("US Dollar Index", "DX-Y.NYB", 2), ("USD/INR", "USDINR%3DX", 2), ("EUR/INR", "EURINR%3DX", 2)]
COMMODITIES = [("Gold (USD/oz)", "GC%3DF", 2), ("Silver (USD/oz)", "SI%3DF", 2), ("Brent crude (USD/bbl)", "BZ%3DF", 2),
               ("WTI crude (USD/bbl)", "CL%3DF", 2), ("Copper (USD/lb)", "HG%3DF", 3),
               ("Gold BeES (NSE ETF, Rs)", "GOLDBEES.NS", 2), ("Silver BeES (NSE ETF, Rs)", "SILVERBEES.NS", 2)]
REITS = [("Embassy Office Parks REIT", "EMBASSY.BO", "REIT"), ("Mindspace Business Parks REIT", "MINDSPACE.BO", "REIT"),
         ("Brookfield India REIT", "BIRET.BO", "REIT"), ("Nexus Select Trust", "NXST.BO", "REIT"),
         ("IndiGrid InvIT", "INDIGRID.BO", "InvIT"), ("PowerGrid InvIT", "PGINVIT.BO", "InvIT"),
         ("IRB InvIT Fund", "IRBINVIT.BO", "InvIT"), ("Cube Highways Trust", "CUBEINVIT.BO", "InvIT")]


def get(url, headers=None, timeout=30, tries=3):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={**UA, **(headers or {})}), timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def fnum(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def pct(a, b):
    return round((a - b) / b * 100, 2) if a is not None and b else None


# ---------------------------------------------------------------- NSE
def nse_indices():
    d = json.loads(get("https://www.nseindia.com/api/allIndices", {"Referer": "https://www.nseindia.com/"}))
    rows = {r["index"]: r for r in d["data"]}
    return rows, d.get("timestamp", ""), d.get("dates", {})


def nse_row(r, label):
    last = fnum(r.get("last"))
    return {"name": label, "value": last, "dp": 2, "d1": fnum(r.get("percentChange")), "w1": pct(last, fnum(r.get("oneWeekAgoVal"))),
            "m1": fnum(r.get("perChange30d")), "y1": fnum(r.get("perChange365d")) or None, "pe": fnum(r.get("pe")) or None, "pb": fnum(r.get("pb")) or None,
            "dy": fnum(r.get("dy")), "adv": int(r["advances"]) if str(r.get("advances", "")).isdigit() else None,
            "dec": int(r["declines"]) if str(r.get("declines", "")).isdigit() else None,
            "high52": fnum(r.get("yearHigh")), "low52": fnum(r.get("yearLow"))}


def nse_flows():
    d = json.loads(get("https://www.nseindia.com/api/fiidiiTradeReact", {"Referer": "https://www.nseindia.com/"}))
    out = {"date": None}
    for r in d:
        k = "fii" if r["category"].upper().startswith("FII") else "dii"
        out[k] = {"buy": fnum(r["buyValue"]), "sell": fnum(r["sellValue"]), "net": fnum(r["netValue"])}
        out["date"] = r["date"]
    return out


# ---------------------------------------------------------------- Yahoo
def yahoo(sym, dp, name, max_age_days=7, bp=False):
    """Return a row with last, 1D, 1W, 1M, 1Y from Yahoo's chart endpoint, or None if stale or unavailable."""
    try:
        d = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1y&interval=1d"))
        r = d["chart"]["result"][0]
        ts = r["timestamp"]
        cl = r["indicators"]["quote"][0]["close"]
        pts = [(t, c) for t, c in zip(ts, cl) if c is not None]
        meta = r["meta"]
        if (time.time() - meta["regularMarketTime"]) / 86400 > max_age_days:
            return None            # stale quote (Yahoo's NSE REIT tickers are years old): better nothing than wrong
        last = meta.get("regularMarketPrice") or pts[-1][1]
        # Yahoo's last daily bar is usually today's (still forming or just closed): the day before it is then the "previous close".
        if len(pts) >= 2 and abs(pts[-1][0] - meta["regularMarketTime"]) < 0.9 * 86400:
            prev = pts[-2][1]
        elif len(pts) >= 1 and len(pts) < 2:
            prev = meta.get("previousClose") or meta.get("chartPreviousClose") or pts[-1][1]
        else:
            prev = pts[-1][1]

        def back(days):
            target = meta["regularMarketTime"] - days * 86400
            older = [c for t, c in pts if t <= target]
            return older[-1] if older else None
        when = datetime.fromtimestamp(meta["regularMarketTime"], IST).strftime("%d %b %Y %H:%M IST")
        if bp:      # a yield: the change that matters is in basis points (1 bp = 0.01 percentage point), not percent
            def diff(x):
                return round((last - x) * 100, 1) if x is not None else None
            return {"name": name, "value": round(last, dp), "dp": dp, "unit": "bp", "d1": diff(prev), "w1": diff(back(7)),
                    "m1": diff(back(30)), "y1": diff(back(365)), "asof": when}
        return {"name": name, "value": round(last, dp), "dp": dp, "d1": pct(last, prev), "w1": pct(last, back(7)),
                "m1": pct(last, back(30)), "y1": pct(last, back(365)), "asof": when}
    except Exception as e:  # noqa: BLE001
        print(f"  yahoo {sym} failed: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------- RBI, G-Sec
def rbi_rates():
    t = get("https://www.rbi.org.in/")
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t)).replace("\xa0", " "))
    want = [("Policy repo rate", r"Policy Repo Rate\s*:\s*([\d.]+)%"), ("Standing Deposit Facility rate", r"Standing Deposit Facility Rate\s*:\s*([\d.]+)%"),
            ("Marginal Standing Facility rate", r"Marginal Standing Facility Rate\s*:\s*([\d.]+)%"), ("Bank rate", r"Bank Rate\s*:\s*([\d.]+)%"),
            ("Fixed reverse repo rate", r"Fixed Reverse Repo Rate\s*:\s*([\d.]+)%"), ("CRR", r"CRR\s*:\s*([\d.]+)%"), ("SLR", r"SLR\s*:\s*([\d.]+)%")]
    out = []
    for label, rx in want:
        m = re.search(rx, t)
        if m:
            out.append({"name": label, "value": float(m.group(1))})
    return out


def gsec_10y():
    s = get("https://in.tradingview.com/symbols/TVC-IN10Y/")
    m = re.search(r'"price":\s*([\d.]+)', s)
    if not m:
        return None
    v = float(m.group(1))
    return {"name": "India 10-year G-Sec yield (%)", "value": round(v, 3), "dp": 3} if 3 < v < 12 else None


# ---------------------------------------------------------------- main
def main():
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    now = datetime.now(IST)
    out = {"updated": now.strftime("%Y-%m-%d %H:%M IST"), "notes": []}

    try:
        rows, stamp, dates = nse_indices()
        out["nse_stamp"] = stamp
        out["indices"] = [nse_row(rows[k], lab) for k, lab in INDEX_ROWS if k in rows]
        out["sectors"] = [nse_row(rows[k], lab) for k, lab in SECTOR_ROWS if k in rows]
        for r in out["indices"] + out["sectors"]:
            r["source"] = "NSE"
        out["periods"] = dates
        # sanity: a one-day move beyond 20% on a broad index means a parsing problem, not a market
        assert all(abs(r["d1"]) < 20 for r in out["indices"] if r["d1"] is not None)
    except Exception as e:  # noqa: BLE001
        print(f"NSE index feed failed: {e}", file=sys.stderr)
        out["notes"].append("NSE index feed unavailable this run; main indices come from Yahoo Finance and sector detail is limited.")
        fallback = [("Nifty 50", "%5ENSEI"), ("Nifty Bank", "%5ENSEBANK"), ("Nifty Next 50", "%5ENSMIDCP"), ("India VIX", "%5EINDIAVIX"),
                    ("Sensex", "%5EBSESN")]
        out["indices"] = [r for r in (yahoo(s, 2, n) for n, s in fallback) if r]
        for r in out["indices"]:
            r["source"] = "Yahoo Finance"
        sec = [("IT", "%5ECNXIT"), ("Pharma", "%5ECNXPHARMA"), ("FMCG", "%5ECNXFMCG"), ("Auto", "%5ECNXAUTO"), ("Metal", "%5ECNXMETAL"),
               ("Realty", "%5ECNXREALTY"), ("Energy", "%5ECNXENERGY"), ("PSU Banks", "%5ECNXPSUBANK"), ("Financial Services", "%5ECNXFIN"),
               ("Infra", "%5ECNXINFRA"), ("PSE", "%5ECNXPSE"), ("Media", "%5ECNXMEDIA")]
        out["sectors"] = [r for r in (yahoo(s, 2, n) for n, s in sec) if r]
        for r in out["sectors"]:
            r["source"] = "Yahoo Finance"

    # Sensex is not in the NSE feed; it comes from Yahoo alongside the NSE indices
    if not any(r["name"] == "Sensex" for r in out["indices"]):
        sx = yahoo("%5EBSESN", 2, "Sensex")
        if sx:
            sx["source"] = "Yahoo Finance"
            out["indices"].insert(1, sx)

    try:
        out["flows"] = nse_flows()
    except Exception as e:  # noqa: BLE001
        print(f"FII/DII feed failed: {e}", file=sys.stderr)
        out["flows"] = old.get("flows")
        out["notes"].append("FII/DII flows could not be refreshed this run; the previous figures are shown with their own date.")

    for key, table, src in (("global", GLOBAL, "Yahoo Finance"), ("rates_fx", RATES_FX, "Yahoo Finance"), ("commodities", COMMODITIES, "Yahoo Finance")):
        out[key] = []
        for name, sym, dp in table:
            r = yahoo(sym, dp, name, bp="yield" in name.lower() or "bill" in name.lower())
            if r:
                r["source"] = src
                out[key].append(r)
    g, s = {r["name"]: r for r in out["commodities"]}.get("Gold (USD/oz)"), {r["name"]: r for r in out["commodities"]}.get("Silver (USD/oz)")
    if g and s and s["value"]:
        out["gold_silver_ratio"] = round(g["value"] / s["value"], 2)

    out["reits"] = []
    for name, sym, kind in REITS:
        r = yahoo(sym, 2, name)
        if r:
            r.update(kind=kind, source="Yahoo Finance (BSE ticker)")
            out["reits"].append(r)

    try:
        out["policy_rates"] = rbi_rates()
    except Exception as e:  # noqa: BLE001
        print(f"RBI rates failed: {e}", file=sys.stderr)
        out["policy_rates"] = old.get("policy_rates", [])
    try:
        y10 = gsec_10y()
        if y10:
            y10["source"] = "TradingView (best effort)"
            out["gsec10y"] = y10
    except Exception as e:  # noqa: BLE001
        print(f"G-Sec 10Y failed: {e}", file=sys.stderr)
    if "gsec10y" not in out and old.get("gsec10y"):
        out["gsec10y"] = old["gsec10y"]
        out["notes"].append("The India 10-year yield could not be refreshed this run; the previous reading is shown.")

    # A run that produced almost nothing should not overwrite a good file.
    if len(out.get("indices", [])) < 3 and old.get("indices"):
        print("too little data fetched; keeping the previous file", file=sys.stderr)
        return
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"market: {len(out['indices'])} indices, {len(out['sectors'])} sectors, {len(out['global'])} global, {len(out['commodities'])} commodities, "
          f"{len(out['reits'])} REIT/InvIT, {len(out['policy_rates'])} RBI rates, flows={'yes' if out.get('flows') else 'no'}")


if __name__ == "__main__":
    main()
