"""Company snapshots and event-impact estimates for the Listed Universe desk.

Same rules as the other desks: Python standard library only, no API keys, no AI service.
    python scripts/company_intel.py             # normal run
    python scripts/company_intel.py --max 700   # first fill: fetch up to 700 companies

Reads data/listed.json (written by fetch_listed.py) and writes:
  data/companies.json - per company: what it does, sector, market cap, revenue / net profit or loss / operating cash flow /
                        free cash flow / debt for the last reported years. Source: Yahoo Finance (public endpoints, INR).
                        Nifty 100 refreshed weekly; other companies are fetched when first seen (a batch per run) and
                        re-read after 30 days.
  data/listed.json    - each item gains "ckey" (which company snapshot it belongs to) and "impact".

"Impact" is a rule-based size check, not a forecast: the amount in the event (when the filing or headline states one) is
compared with the company's yearly revenue, market value or profit, and the level (High / Medium / Low) follows fixed
thresholds written below. When no amount is stated the level is "Not stated" and the card says what to look for.
Hand-written business notes live in data/company_notes.json (Nifty 100) and never come from this script.
"""
import calendar, html, http.cookiejar, json, re, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LISTED = ROOT / "data" / "listed.json"
COMP = ROOT / "data" / "companies.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
IST = timezone(timedelta(hours=5, minutes=30))
NIFTY_REFRESH_DAYS = 7
OTHER_REFRESH_DAYS = 30
CRORE = 1e7
TS_TYPES = ["TotalRevenue", "NetIncome", "OperatingCashFlow", "FreeCashFlow", "TotalDebt"]
DEFAULT_MAX = 400
MISSING_RETRY_DAYS = 7
ALGO = "v2"                 # entries marked missing by an older version of this script are tried again
SCREENER_BLOCKED = False


# ---------------------------------------------------------------- Yahoo Finance
class Yahoo:
    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.op.addheaders = [("User-Agent", UA), ("Accept", "application/json,*/*")]
        self.crumb = None
        self.blocked = False

    def _get(self, url):
        with self.op.open(url, timeout=30) as r:
            return r.read().decode("utf-8", "replace")

    def login(self):
        try:
            try:
                self._get("https://fc.yahoo.com")
            except Exception:  # noqa: BLE001  (404 is normal, it still sets the cookie)
                pass
            self.crumb = self._get("https://query2.finance.yahoo.com/v1/test/getcrumb").strip()
            return bool(self.crumb) and "<" not in self.crumb
        except Exception as e:  # noqa: BLE001
            print(f"  yahoo login failed: {e}", file=sys.stderr)
            return False

    def json(self, url):
        for attempt in range(2):
            try:
                return json.loads(self._get(url))
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    self.blocked = True
                    print("  yahoo rate limit (429): stopping fetches for this run", file=sys.stderr)
                    return None
                if e.code == 401 and attempt == 0 and self.login():
                    url = re.sub(r"crumb=[^&]*", "crumb=" + urllib.parse.quote(self.crumb), url)
                    continue
                return None
            except Exception:  # noqa: BLE001
                time.sleep(1)
        return None

    def usd_inr(self):
        j = self.json("https://query1.finance.yahoo.com/v8/finance/chart/INR=X?range=5d&interval=1d")
        try:
            return float(j["chart"]["result"][0]["meta"]["regularMarketPrice"])
        except Exception:  # noqa: BLE001
            return 88.0

    def company(self, ysym):
        q = urllib.parse.quote(ysym)
        mods = "assetProfile,price,financialData,summaryDetail"
        j = self.json(f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{q}?modules={mods}&crumb={urllib.parse.quote(self.crumb or '')}")
        try:
            r = j["quoteSummary"]["result"][0]
        except Exception:  # noqa: BLE001
            return None
        prof, price, fd, sd = r.get("assetProfile", {}), r.get("price", {}), r.get("financialData", {}), r.get("summaryDetail", {})
        raw = lambda d, k: (d.get(k) or {}).get("raw") if isinstance(d.get(k), dict) else None  # noqa: E731
        types = ",".join(f"{p}{t}" for t in TS_TYPES for p in ("annual", "trailing"))
        t = self.json("https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/"
                      f"{q}?type={types}&period1=1420070400&period2={int(time.time()) + 86400}")
        series = {}
        try:
            for blk in t["timeseries"]["result"]:
                key = blk["meta"]["type"][0]
                series[key] = [(x["asOfDate"], x["reportedValue"]["raw"], x.get("currencyCode")) for x in blk.get(key, []) if x and x.get("reportedValue")]
        except Exception:  # noqa: BLE001
            pass
        years = {}
        cur = None
        for t_name, field in (("TotalRevenue", "revenue"), ("NetIncome", "net_income"), ("OperatingCashFlow", "ocf"),
                              ("FreeCashFlow", "fcf"), ("TotalDebt", "debt")):
            for d, v, c in series.get("annual" + t_name, []):
                years.setdefault(d, {})[field] = round(v / CRORE, 1)
                cur = cur or c
        ttm = {}
        for t_name, field in (("TotalRevenue", "revenue"), ("NetIncome", "net_income"), ("OperatingCashFlow", "ocf"), ("FreeCashFlow", "fcf")):
            v = series.get("trailing" + t_name, [])
            if v:
                ttm[field] = round(v[-1][1] / CRORE, 1)
                ttm["asof"] = v[-1][0]
        if ttm and ttm.get("asof", "") < (datetime.now(IST) - timedelta(days=300)).strftime("%Y-%m-%d"):
            ttm = {}          # a trailing figure that old is stale; show the annual years only
        yl = [dict(asof=d, **years[d]) for d in sorted(years)][-3:]
        mcap = raw(price, "marketCap") or raw(sd, "marketCap")
        return {
            "ysym": ysym, "name": price.get("longName") or price.get("shortName") or "", "sector": prof.get("sectorDisp") or "",
            "industry": prof.get("industryDisp") or "", "summary": (prof.get("longBusinessSummary") or "")[:900], "website": prof.get("website") or "",
            "currency": cur or price.get("financialCurrency") or price.get("currency") or "",
            "mcap_cr": round(mcap / CRORE, 0) if mcap else None, "years": yl, "ttm": ttm,
            "rev_growth": raw(fd, "revenueGrowth"), "earn_growth": raw(fd, "earningsGrowth"), "net_margin": raw(fd, "profitMargins"),
            "fetched": datetime.now(IST).strftime("%Y-%m-%d"),
        }


# ---------------------------------------------------------------- Screener.in (fallback and the main source for BSE-only companies)
def _txt(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _num(s):
    s = _txt(s).replace(",", "").replace("%", "").replace("₹", "").replace("Cr.", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _month_end(label):
    """'Mar 2026' -> '2026-03-31'."""
    try:
        d = datetime.strptime(label, "%b %Y")
        return f"{d.year}-{d.month:02d}-{calendar.monthrange(d.year, d.month)[1]:02d}"
    except ValueError:
        return None


def _section(page, sec):
    i = page.find(f'id="{sec}"')
    if i < 0:
        return ""
    j = page.find("</section>", i)
    return page[i:j if j > 0 else i + 20000]


def _table(section):
    """{row label: [values]} and the header labels, from one Screener statement section."""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", section, re.S)
    header, data = [], {}
    for r in rows:
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, re.S)
        if not cells:
            continue
        label = _txt(cells[0]).replace("+", "").strip()
        if not header and not label and len(cells) > 2:
            header = [_txt(c) for c in cells[1:]]
            continue
        if label:
            data[label] = [_num(c) for c in cells[1:]]
    return header, data


def screener_company(key):
    """One company page from screener.in. Returns the same shape as Yahoo.company(), or None. 429 -> sets SCREENER_BLOCKED."""
    global SCREENER_BLOCKED
    url = f"https://www.screener.in/company/{urllib.parse.quote(key)}/consolidated/"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
        with urllib.request.urlopen(req, timeout=40) as r:
            page = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 429:
            SCREENER_BLOCKED = True
            print("  screener rate limit (429): stopping screener fetches for this run", file=sys.stderr)
        return None
    except Exception:  # noqa: BLE001
        return None
    if 'id="top-ratios"' not in page:
        return None
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
    about = re.search(r'class="sub show-more-box about"[^>]*>(.*?)</div>', page, re.S)
    sector = re.search(r'title="Sector">(.*?)</a>', page, re.S)
    industry = re.search(r'title="Industry">(.*?)</a>', page, re.S) or re.search(r'title="Broad Industry">(.*?)</a>', page, re.S)
    ratios = {}
    tr = page[page.find('id="top-ratios"'):]
    for li in re.findall(r"<li[^>]*>(.*?)</li>", tr[: tr.find("</ul>")], re.S):
        nm = re.search(r'class="name"[^>]*>(.*?)</span>', li, re.S)
        vv = re.search(r'class="number"[^>]*>(.*?)</span>', li, re.S)
        if nm and vv:
            ratios[_txt(nm.group(1))] = _num(vv.group(1))
    ph, pl = _table(_section(page, "profit-loss"))
    ch, cf = _table(_section(page, "cash-flow"))
    bh, bs = _table(_section(page, "balance-sheet"))
    qh, _q = _table(_section(page, "quarters"))

    def pick(tbl, *prefixes):
        for lab, vals in tbl.items():
            if any(lab.lower().startswith(p) for p in prefixes):
                return vals
        return None

    rev = pick(pl, "sales", "revenue")
    npf = pick(pl, "net profit")
    ocf = pick(cf, "cash from operating")
    fcf = pick(cf, "free cash flow")
    debt = pick(bs, "borrowing")
    years = {}
    for h, series in ((ph, {"revenue": rev, "net_income": npf}), (ch, {"ocf": ocf, "fcf": fcf}), (bh, {"debt": debt})):
        for idx, lab in enumerate(h):
            asof = _month_end(lab)
            if not asof:
                continue
            for f, vals in series.items():
                if vals and idx < len(vals) and vals[idx] is not None:
                    years.setdefault(asof, {})[f] = vals[idx]
    yl = [dict(asof=d, **years[d]) for d in sorted(years) if years[d].get("revenue") is not None or years[d].get("net_income") is not None][-3:]
    ttm = {}
    if "TTM" in ph:
        i = ph.index("TTM")
        for f, vals in (("revenue", rev), ("net_income", npf)):
            if vals and i < len(vals) and vals[i] is not None:
                ttm[f] = vals[i]
        qd = _month_end(qh[-1]) if qh else None
        if ttm and qd:
            ttm["asof"] = qd
    mc = ratios.get("Market Cap")
    return {
        "ysym": "", "source": "Screener.in", "name": _txt(h1.group(1)) if h1 else "", "sector": _txt(sector.group(1)) if sector else "",
        "industry": _txt(industry.group(1)) if industry else "", "summary": _txt(about.group(1))[:900] if about else "", "website": "",
        "currency": "INR", "mcap_cr": round(mc) if mc else None, "years": yl, "ttm": ttm, "rev_growth": None, "earn_growth": None, "net_margin": None,
        "pe": ratios.get("Stock P/E"), "roce": ratios.get("ROCE"), "roe": ratios.get("ROE"), "book_value": ratios.get("Book Value"),
        "div_yield": ratios.get("Dividend Yield"), "fetched": datetime.now(IST).strftime("%Y-%m-%d"),
    }


def has_data(c):
    return bool(c and (c.get("years") or c.get("ttm") or c.get("summary")))


def ysym_of(ckey):
    if ckey.startswith("BSE:"):
        return ckey[4:] + ".BO"
    return ckey + ".NS"


# ---------------------------------------------------------------- amounts in the event text
AMT = re.compile(r"(?:(?P<cur>₹|Rs\.?|INR|US\$|USD|\$)\s?)?(?P<num>\d[\d,]*(?:\.\d+)?)\s?(?P<unit>crores?|cr\b|lakhs?|million|mn\b|billion|bn\b)", re.I)


def amounts_cr(text, usd_inr):
    """Every money amount in the text that carries a unit, converted to rupees crore. Amounts with no unit are ignored."""
    out = []
    for m in AMT.finditer(text or ""):
        try:
            n = float(m.group("num").replace(",", ""))
        except ValueError:
            continue
        unit, cur = m.group("unit").lower(), (m.group("cur") or "").lower()
        usd = cur in ("us$", "usd", "$")
        if unit.startswith("cr"):
            v = n
        elif unit.startswith("lakh"):
            v = n * 0.01
        elif unit in ("million", "mn"):
            v = n * (usd_inr / 10 if usd else 0.1)
        else:
            v = n * (usd_inr * 100 if usd else 100)
        if not cur and unit in ("million", "mn", "billion", "bn"):
            continue           # a bare "5 million" could be anything (shares, users); only count it when a currency is named
        out.append(v)
    return out


# ---------------------------------------------------------------- impact
def fmt_cr(v):
    if v is None:
        return "n/a"
    if abs(v) >= 100000:
        return f"₹{v / 100000:,.2f} lakh crore"
    return f"₹{v:,.0f} crore"


def size_of(co):
    """(revenue, net income, market cap, debt) in crore from the snapshot, latest annual first, else trailing."""
    if not co:
        return None, None, None, None
    last = co["years"][-1] if co.get("years") else {}
    rev = last.get("revenue") or co.get("ttm", {}).get("revenue")
    ni = last.get("net_income") if "net_income" in last else co.get("ttm", {}).get("net_income")
    return rev, ni, co.get("mcap_cr"), last.get("debt")


def level_from(pct, hi, mid):
    return "High" if pct >= hi else "Medium" if pct >= mid else "Low"


def assess(it, co, usd_inr):
    text = f"{it['title']} {it.get('summary', '')}"
    cat = it["category"]
    rev, ni, mcap, debt = size_of(co)
    amts = amounts_cr(text, usd_inr)
    amt = max(amts) if amts else None
    basis, level = [], "Not stated"
    have = co is not None and (rev or mcap)
    ctx = f"Company size for comparison: revenue {fmt_cr(rev)}" + (f", market value {fmt_cr(mcap)}" if mcap else "") + "." if have else "No financial data is on file for this company, so the event cannot be sized against it."

    if cat in ("Orders & Contracts", "Business Updates") and amt and rev:
        pct = amt / rev * 100
        level = level_from(pct, 10, 2)
        basis += [f"Amount in the text: about {fmt_cr(amt)}, which is {pct:.1f}% of its latest yearly revenue ({fmt_cr(rev)}).",
                  "Orders, contracts and projects are usually delivered or built over several years, so the effect in any one year is smaller."]
    elif cat in ("Deals & M&A", "Capital Raising") and amt and mcap:
        pct = amt / mcap * 100
        level = level_from(pct, 10, 2)
        what = "deal" if cat == "Deals & M&A" else ("borrowing" if re.search(r"debenture|ncd|bond|loan|borrow", text, re.I) else "fund-raise")
        basis += [f"Amount in the text: about {fmt_cr(amt)}, which is {pct:.1f}% of the company's market value ({fmt_cr(mcap)}).",
                  ("Paying for a deal can add debt or dilute shareholders; a larger share of market value means a bigger change to the company."
                   if what == "deal" else
                   "New shares dilute existing holders; new borrowing adds interest cost. A larger share of market value means a bigger change.")]
    elif cat == "Payouts & Buybacks":
        if re.search(r"buy-?back", text, re.I) and amt and mcap:
            pct = amt / mcap * 100
            level = level_from(pct, 5, 1)
            basis.append(f"Buyback of about {fmt_cr(amt)} is {pct:.1f}% of market value ({fmt_cr(mcap)}); it shrinks the share count and returns cash.")
        else:
            level = "Low"
            basis.append("Cash returned to shareholders or a bonus/split; it does not change what the business earns." + (f" Last reported net profit: {fmt_cr(ni)}." if ni is not None else ""))
    elif cat == "Legal & Regulatory":
        if re.search(r"insolvency|\bcirp\b|creditors", text, re.I):
            level = "High"
            basis.append("Insolvency proceedings can put creditors in control and leave shareholders last in line for any recovery.")
        elif amt and (ni and ni > 0 or mcap):
            ref, label = (ni, "yearly net profit") if ni and ni > 0 else (mcap, "market value")
            pct = amt / ref * 100
            level = level_from(pct, 10, 2)
            basis.append(f"Amount in the text: about {fmt_cr(amt)}, which is {pct:.1f}% of its {label} ({fmt_cr(ref)}).")
        else:
            basis.append("No rupee amount is stated in the text. Open the original: a penalty, a stop-order or a court ruling on a core product matters far more than a routine notice.")
    elif cat == "Operations & Risk":
        if re.search(r"default|fraud", text, re.I):
            level = "High"
            basis.append("Default or fraud can cut off funding and damage trust; treat it as serious until the company quantifies it.")
        else:
            basis.append("A disruption (fire, strike, outage, recall) matters in proportion to the share of output or revenue it stops, which the filing often states.")
    elif cat == "Management":
        if re.search(r"\bceo\b|managing director|\bmd\b|\bcfo\b|chairman|chief|whole[- ]time", text, re.I):
            level = "Medium"
            basis.append("A change at the top can shift strategy and investor confidence. Look at who replaces them, whether it was planned, and the reason given.")
        else:
            level = "Low"
            basis.append("A routine governance change; it rarely alters the business by itself.")
    elif cat == "Ratings":
        if re.search(r"downgrad|withdraw", text, re.I):
            level = "High" if (debt and mcap and debt > mcap * 0.5) else "Medium"
            basis.append("A rating downgrade raises the cost of borrowing." + (f" Debt on the books: {fmt_cr(debt)}." if debt else ""))
        elif re.search(r"upgrad", text, re.I):
            level = "Low"
            basis.append("An upgrade lowers the cost of borrowing; a mild positive.")
        else:
            basis.append("The filing summary does not say whether the rating went up, down or stayed the same. Open it: only a downgrade or an upgrade changes borrowing cost.")
    elif cat == "Results":
        level = "Check numbers"
        if co and (co.get("rev_growth") is not None or co.get("earn_growth") is not None):
            rg, eg = co.get("rev_growth"), co.get("earn_growth")
            basis.append("Latest data on file: " + ", ".join(x for x in (
                rg is not None and f"revenue {rg * 100:+.1f}% year on year", eg is not None and f"earnings {eg * 100:+.1f}% year on year") if x) + ".")
        basis.append("A results filing matters by how the numbers compare with last year and with what the market expected; read the profit, margin and cash-flow lines in the filing.")
    elif amt and rev and cat in ("Business Updates", "Company News"):
        pct = amt / rev * 100
        level = level_from(pct, 10, 2)
        basis.append(f"Amount in the text: about {fmt_cr(amt)}, which is {pct:.1f}% of latest yearly revenue ({fmt_cr(rev)}). Projects are usually built over several years, so the effect in any one year is smaller.")
    elif cat == "Market Alerts":
        basis.append("An exchange query about a price move or a news item; the company must clarify. The effect depends on its answer.")
    else:
        basis.append("No amount or size is stated, so its effect on the company cannot be measured from the text." + (" Open the original for the numbers." if it.get("url") else ""))
    if level in ("Not stated",) and amt is None and cat in ("Orders & Contracts", "Deals & M&A", "Capital Raising"):
        basis.insert(0, "The filing summary gives no rupee value. Open the filing (the PDF usually has it).")
    if have:
        basis.append(ctx)
    elif co is None:
        basis.append(ctx)
    return {"level": level, "basis": basis, "amount_cr": round(amt, 1) if amt else None}


# ---------------------------------------------------------------- main
def main():
    limit = DEFAULT_MAX
    if "--max" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--max") + 1])
    today = datetime.now(IST).date()
    listed = json.loads(LISTED.read_text(encoding="utf-8"))
    items = listed["items"]
    comp = json.loads(COMP.read_text(encoding="utf-8")) if COMP.exists() else {"companies": {}}
    cos = comp["companies"]

    for it in items:
        s = it.get("symbol") or ""
        it["ckey"] = ("BSE:" + s if it["source"] == "BSE" else s) if s else ""

    def age(k):
        f = cos.get(k, {}).get("fetched")
        return (today - datetime.strptime(f, "%Y-%m-%d").date()).days if f else 10 ** 6

    nifty = sorted({i["ckey"] for i in items if i["universe"] == "nifty100" and i["ckey"]})
    todo = [k for k in nifty if age(k) >= NIFTY_REFRESH_DAYS]
    others = {}
    for i in sorted(items, key=lambda x: (not x["major"], x["date"]), reverse=False):
        if i["universe"] != "nifty100" and i["ckey"] and i["ckey"] not in others:
            others[i["ckey"]] = i
    def recently_missing(k):
        c = cos.get(k, {})
        m = c.get("missing_on")
        return bool(m and c.get("algo") == ALGO and (today - datetime.strptime(m, "%Y-%m-%d").date()).days < MISSING_RETRY_DAYS)

    ordered = sorted(others, key=lambda k: (k in cos, not others[k]["major"]))      # never-seen companies first
    ordered = [k for k in ordered if age(k) >= OTHER_REFRESH_DAYS and not recently_missing(k)]
    todo = [k for k in todo if not recently_missing(k)]
    todo += ordered[: max(0, limit - len(todo))]
    todo = todo[:limit]

    y = Yahoo()
    usd = 88.0
    yahoo_ok = y.login()
    if yahoo_ok:
        usd = y.usd_inr()
    if todo:
        print(f"fetching {len(todo)} companies (USD/INR {usd:.2f}; Yahoo {'on' if yahoo_ok else 'off'})")
        got = {"Yahoo Finance": 0, "Screener.in": 0}
        t0 = time.time()
        for k in todo:
            if time.time() - t0 > 40 * 60:
                print("  time budget reached; the rest continue next run")
                break
            c = None
            code = k[4:] if k.startswith("BSE:") else k
            # NSE companies: Yahoo first, Screener as fallback. BSE-only companies: Screener first (Yahoo does not know BSE scrip codes well).
            order = ("screener", "yahoo") if k.startswith("BSE:") else ("yahoo", "screener")
            for src in order:
                if src == "yahoo" and yahoo_ok and not y.blocked:
                    c = y.company(ysym_of(k))
                    if has_data(c):
                        c["source"] = "Yahoo Finance"
                    time.sleep(0.3)
                elif src == "screener" and not SCREENER_BLOCKED:
                    c = screener_company(code)
                    time.sleep(1.0)
                if has_data(c) and (c.get("years") or c.get("summary")):
                    break
                c = None
            if c:
                c["algo"] = ALGO
                cos[k] = c
                got[c["source"]] += 1
            elif not has_data(cos.get(k)):
                cos[k] = {"fetched": "2000-01-01", "missing_on": str(today), "algo": ALGO}   # nothing anywhere: retry in a week
            # (a refresh that failed keeps the older snapshot rather than wiping it)
        print(f"  snapshots stored: {got}")

    notes = json.loads((ROOT / "data" / "company_notes.json").read_text(encoding="utf-8"))
    for it in items:
        co = cos.get(it["ckey"]) if it["ckey"] else None
        if co and not co.get("years") and not co.get("ttm") and not co.get("summary"):
            co = None
        it["impact"] = assess(it, co, usd) if it["ckey"] else {"level": "Not stated", "amount_cr": None,
                                                                "basis": ["This story is not tied to one listed company, so there is no snapshot to size it against."]}
        if co and not it.get("industry"):
            it["industry"] = co.get("sector") or ""
    comp["updated"] = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
    comp["usd_inr"] = usd
    COMP.write_text(json.dumps(comp, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    LISTED.write_text(json.dumps(listed, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    lv = {}
    for it in items:
        lv[it["impact"]["level"]] = lv.get(it["impact"]["level"], 0) + 1
    print("impact levels:", lv)


if __name__ == "__main__":
    main()
