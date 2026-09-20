"""Collect news about India's listed companies into data/listed.json (the Listed Market Universe desk).

Same rules as the other desks: Python standard library only, no API keys, no AI service.
    python scripts/fetch_listed.py              # normal run: last 3 days of filings, current press feeds
    python scripts/fetch_listed.py --backfill 7 # first fill: last 7 days of filings

Two universes, one file (the "universe" field on every item):
  nifty100 - the 100 companies in the official NSE Nifty 100 list (data/nifty100.json is refreshed from NSE each run)
  other    - every other listed company

Sources, all public:
  NSE corporate announcements  - the company's own filing, with the exchange's one-line summary and a link to the PDF
  BSE corporate announcements  - the same for companies that are only on BSE (skipped when the company is on NSE)
  Press RSS                    - Economic Times, Business Standard, Mint, BusinessLine, Moneycontrol (headline + lead)
  Google News search           - one query per Nifty 100 company (headline + outlet + link only)

Routine filings (AGM notices, trading window, ESOP allotments, newspaper ads) are dropped. What is kept is sorted into
categories (Results, Deals & M&A, Orders, Capital Raising, Payouts, Management, Ratings, Legal & Regulatory,
Operations & Risk, Business Updates, Market Alerts). Nothing is summarised or rewritten by a model.
"""
import csv, html, http.cookiejar, io, json, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "listed.json"
N100 = ROOT / "data" / "nifty100.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
IST = timezone(timedelta(hours=5, minutes=30))
MAX_ITEMS = 4000
KEEP_DAYS = 30
FILING_DAYS = 3          # days of exchange filings re-read on a normal run (overlap is safe, ids de-duplicate)
MAX_OTHER_PER_CO_DAY = 3
BSE_MAX_PAGES = 40

NIFTY_URLS = ["https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
              "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv"]

FEEDS = [  # (outlet, url)
    ("Economic Times", "https://economictimes.indiatimes.com/markets/stocks/news/rssfeeds/2146842.cms"),
    ("Economic Times", "https://economictimes.indiatimes.com/industry/rssfeeds/13352306.cms"),
    ("Business Standard", "https://www.business-standard.com/rss/companies-101.rss"),
    ("Business Standard", "https://www.business-standard.com/rss/markets-106.rss"),
    ("Mint", "https://www.livemint.com/rss/companies"),
    ("BusinessLine", "https://www.thehindubusinessline.com/companies/feeder/default.rss"),
    ("BusinessLine", "https://www.thehindubusinessline.com/markets/feeder/default.rss"),
    ("Moneycontrol", "https://www.moneycontrol.com/rss/business.xml"),
]

# ---------------------------------------------------------------- how a company is recognised in a headline
# Matching is case-sensitive on purpose ("Trent" the company, not "trent"). Auto aliases come from the official name;
# MANUAL replaces the auto alias for names that are common words or that need a context guard.
STOP_FIRST = {"Tata", "Adani", "Bajaj", "Bharat", "Indian", "Hindustan", "State", "Bank", "Power", "Punjab", "Union", "Oil",
              "Tech", "Sun", "Jio", "Larsen", "Mahindra", "Power", "Coal", "Shree", "United", "Divi", "Dr", "Zydus", "Siemens",
              "Avenue", "Max", "HDFC", "SBI", "Solar", "Torrent", "Varun", "Cholamandalam", "Interglobe", "Samvardhana", "Lodha"}
MANUAL = {
    "RELIANCE": r"Reliance Industries|\bRIL\b|Reliance Jio|Reliance Retail|Jio Platforms|\bReliance\b(?! (?:Power|Infra|Communications|Capital|Home|Naval))",
    "TCS": r"\bTCS\b|Tata Consultancy",
    "INFY": r"Infosys",
    "SBIN": r"State Bank of India|\bSBI\b(?! (?:Life|Card|General|Mutual|MF))",
    "LT": r"Larsen (?:&|and) Toubro|\bL&T\b(?! (?:Finance|Technology|Tech))",
    "ITC": r"\bITC\b(?! Hotels)",
    "ETERNAL": r"Zomato|Blinkit|\bEternal\b(?= (?:Ltd|Limited|shares?|stock|Q[1-4]|board|results|CEO|founder|says|reports|posts|net|profit|raises|launches|to ))",
    "TRENT": r"Westside|Zudio|\bTrent\b(?= (?:Ltd|Limited|shares?|stock|Q[1-4]|board|results|net|profit|revenue|sales|posts|reports|says|to ))",
    "LTM": r"LTIMindtree|LTI Mindtree|\bLTM\b(?= (?:Ltd|Limited|shares?|stock|Q[1-4]|board|results|net|profit))",
    "TITAN": r"Titan Company|\bTitan\b(?! (?:Submersible|Pharma|Intelligence|Comics))|Tanishq",
    "RECLTD": r"Rural Electrification|\bREC\b(?= (?:Ltd|Limited|shares?|stock|Q[1-4]|board|results|net|profit|to |loan|disburse))",
    "BEL": r"Bharat Electronics|\bBEL\b(?= (?:shares?|stock|Q[1-4]|order|bags|Ltd|wins|secures|board|results))",
    "HAL": r"Hindustan Aeronautics|\bHAL\b",
    "M&M": r"Mahindra (?:&|and) Mahindra|\bM&M\b(?! Financial)",
    "HINDUNILVR": r"Hindustan Unilever|\bHUL\b",
    "HDFCBANK": r"HDFC Bank",
    "HDFCAMC": r"HDFC Asset Management|HDFC AMC",
    "HDFCLIFE": r"HDFC Life",
    "SBILIFE": r"SBI Life",
    "BAJAJ-AUTO": r"Bajaj Auto",
    "BAJFINANCE": r"Bajaj Finance(?! Ltd\.? Ltd)",
    "BAJAJFINSV": r"Bajaj Finserv",
    "BAJAJHLDNG": r"Bajaj Holdings",
    "BHARTIARTL": r"Bharti Airtel|\bAirtel\b",
    "INDIGO": r"IndiGo|InterGlobe Aviation",
    "DMART": r"Avenue Supermarts|\bDMart\b|D-Mart",
    "INDHOTEL": r"Indian Hotels|\bIHCL\b|Taj Hotels",
    "IRFC": r"Indian Railway Finance|\bIRFC\b",
    "IOC": r"Indian Oil|\bIOC\b|\bIOCL\b",
    "BPCL": r"Bharat Petroleum|\bBPCL\b",
    "ONGC": r"\bONGC\b|Oil (?:&|and) Natural Gas",
    "NTPC": r"\bNTPC\b(?! Green)",
    "POWERGRID": r"Power Grid|\bPGCIL\b",
    "PFC": r"Power Finance Corporation|\bPFC\b",
    "PNB": r"Punjab National Bank|\bPNB\b(?! Housing)",
    "BANKBARODA": r"Bank of Baroda|\bBoB\b",
    "KOTAKBANK": r"Kotak Mahindra Bank|Kotak Bank",
    "HCLTECH": r"HCLTech|HCL Tech",
    "DRREDDY": r"Dr\.? Reddy",
    "DIVISLAB": r"Divi'?s Lab",
    "SUNPHARMA": r"Sun Pharma",
    "TORNTPHARM": r"Torrent Pharma",
    "ZYDUSLIFE": r"Zydus Lifesciences|Zydus Life",
    "EICHERMOT": r"Eicher Motors|Royal Enfield",
    "TVSMOTOR": r"TVS Motor",
    "MARUTI": r"Maruti Suzuki|\bMaruti\b",
    "HYUNDAI": r"Hyundai Motor India|Hyundai India",
    "MOTHERSON": r"Samvardhana Motherson|\bMotherson\b",
    "MAZDOCK": r"Mazagon? Dock|Mazagoan Dock",
    "LODHA": r"Lodha Developers|Macrotech Developers|\bLodha\b",
    "CHOLAFIN": r"Cholamandalam Investment|\bChola(?:mandalam)? Finance\b|\bCholamandalam\b",
    "JIOFIN": r"Jio Financial|\bJioFin\b",
    "TATACAP": r"Tata Capital",
    "TATACONSUM": r"Tata Consumer",
    "TATAPOWER": r"Tata Power",
    "TATASTEEL": r"Tata Steel",
    "TMPV": r"Tata Motors Passenger|Tata Motors PV|Jaguar Land Rover|\bJLR\b|\bTMPV\b",
    "TMCV": r"Tata Motors Commercial|Tata Motors CV|\bTMCV\b|\bTata Motors\b(?! (?:Passenger|PV))",
    "ENRIN": r"Siemens Energy",
    "SIEMENS": r"\bSiemens\b(?! Energy)",
    "SOLARINDS": r"Solar Industries",
    "CGPOWER": r"CG Power",
    "AXISBANK": r"Axis Bank", "ICICIBANK": r"ICICI Bank", "CANBK": r"Canara Bank", "UNIONBANK": r"Union Bank of India",
    "VBL": r"Varun Beverages|\bVBL\b", "UNITDSPR": r"United Spirits", "MAXHEALTH": r"Max Healthcare",
    "APOLLOHOSP": r"Apollo Hospitals", "SHREECEM": r"Shree Cement", "ULTRACEMCO": r"UltraTech", "AMBUJACEM": r"Ambuja Cements",
    "JINDALSTEL": r"Jindal Steel", "JSWSTEEL": r"JSW Steel", "HINDZINC": r"Hindustan Zinc", "COALINDIA": r"Coal India",
    "SHRIRAMFIN": r"Shriram Finance", "MUTHOOTFIN": r"Muthoot Finance", "GODREJCP": r"Godrej Consumer",
    "CUMMINSIND": r"Cummins India", "ABB": r"\bABB India\b", "BOSCHLTD": r"\bBosch (?:Ltd|India|Limited)\b",
    "NESTLEIND": r"Nestl[eé] India", "TECHM": r"Tech Mahindra", "GAIL": r"\bGAIL\b", "DLF": r"\bDLF\b",
    "ADANIENSOL": r"Adani Energy Solutions", "ADANIENT": r"Adani Enterprises", "ADANIGREEN": r"Adani Green",
    "ADANIPORTS": r"Adani Ports", "ADANIPOWER": r"Adani Power",
}
SUFFIX = re.compile(r"\b(?:Ltd|Limited|Corporation|Corp|Company|Co|Inc)\b\.?", re.I)


def norm(t):
    """Normalised company name for matching filings across exchanges."""
    t = re.sub(r"\b(?:ltd|limited|the|pvt|private)\b\.?", " ", t.lower())
    return re.sub(r"[^a-z0-9]+", "", t)


# ---------------------------------------------------------------- how a filing or headline is classified
# (category, tier, pattern on the exchange's own subject line). Tier 3 = major, 2 = worth keeping, 1 = routine, 0 = drop.
FILING_RULES = [
    ("Legal & Regulatory", 2, r"committee of creditors|\bcoc\b"),
    ("Legal & Regulatory", 3, r"insolvency|\bcirp\b|action\(s\) (?:taken|initiated)|orders? passed|litigation|penalty|show cause|adjudicat|sebi order|search and seizure|\bnclt\b"),
    ("Operations & Risk", 3, r"disruption of operations|fraud|default|fire\b|lock-?out|strike|cyber|data breach|force majeure"),
    ("Deals & M&A", 3, r"amalgamation|merger|scheme of arrangement|acquisition|divest|sale of (?:business|undertaking|stake)|disposal|takeover|open offer|delist|demerger|other restructuring|joint venture|slump sale"),
    ("Deals & M&A", 2, r"agreements?\b|arrangements? for strategic|tie[- ]?up|memorandum of understanding|\bmou\b|collaborat"),
    ("Orders & Contracts", 2, r"bagging|receiving of orders?|awarding of order|order win|contract"),
    ("Payouts & Buybacks", 3, r"buy-?back"),
    ("Payouts & Buybacks", 2, r"dividend|record date|bonus|stock split|sub-?division|book closure|interest payment"),
    ("Capital Raising", 2, r"issue of securities|preferential|rights issue|\bqip\b|fund ?raising|non-convertible|debentures?|warrants?|\becb\b|fundraise"),
    ("Ratings", 2, r"credit rating"),
    ("Results", 2, r"financial results|outcome of board|results\b|earnings"),
    ("Management", 2, r"change in management|change in director|resignation|cessation|change in auditors|appointment of (?:ceo|md|managing|chief|cfo|chairman)|key managerial"),
    ("Market Alerts", 2, r"spurt in volume|rumou?r verification|news verification|clarification|price movement"),
    ("Business Updates", 2, r"product launch|commencement of commercial|capacity|expansion|press release|new plant|approval"),
    ("Business Updates", 1, r"investor presentation|analysts?/institutional|analyst / investor"),
]
FILING_RULES = [(c, t, re.compile(p, re.I)) for c, t, p in FILING_RULES]
# words in the filing text that rescue an otherwise routine "General Update" and give it a category
MATERIAL = re.compile(
    r"acqui|stake|order(?:s)? (?:worth|valued|of)|penalt|fraud|raid|default|insolven|\bfire\b|shut ?down|recall|usfda|"
    r"(?:crore|billion|million).{0,40}(?:order|invest|acqui|fund|loan|penalt|capex|contract)|(?:order|invest|acqui|fund|loan|penalt|capex|contract).{0,40}(?:crore|billion|million)|"
    r"resign|\bceo\b|managing director|chief financial|downgrade|upgrade|open offer|delist|plant|capacity|fda\b|news item|media report|price movement", re.I)
SENIOR = re.compile(r"\bceo\b|managing director|\bmd\b|\bcfo\b|chief|chairman|whole[- ]time|promoter|resign.{0,50}auditor|auditor.{0,50}resign", re.I)
DROP_DESC = re.compile(
    r"shareholders? meeting|newspaper publication|trading window|esop|esos|esps|allotment of|agm|egm|postal ballot|annual report|"
    r"corrigendum|addendum|copy of newspaper|book closure$|change of name|loss of share certificate|duplicate|"
    r"reg\.? ?34|record date for|analyst|independent director|committee meeting|amendment to aoa|amendments? to memorandum|compliance certificate|"
    r"reconciliation|shareholding pattern|voting results|scrutini[sz]er|closure of trading|certificate under", re.I)


PRE_DROP = re.compile(r"reply to clarification|disclosures? under reg\.? ?(?:29|30\(|31)|\bsast\b|takeover regulations|substantial acquisition|"
                      r"insider trading|regulation 7\(|structured digital", re.I)


GENERIC_DESC = re.compile(r"^(?:general(?: updates?)?|updates?|appointment|outcome without intimation|others?)$", re.I)


def filing_head(desc, text, quoted_ok):
    """The line shown as the headline: the filing's own title when it has one, else what the company says it is about."""
    q = re.search(r'titled\s+["“](.+?)["”]', text)
    if q and quoted_ok:
        return q.group(1)
    if GENERIC_DESC.match(desc or ""):
        t = re.sub(r"^.*?informed the exchange\s+(?:about|regarding|that)\s*", "", text, flags=re.I).strip(" .:-'\"")
        if t:
            return trim(t, 150)
    return desc


def classify_filing(desc, text):
    """Return (category, tier). Routine filings come back tier 0."""
    d = desc or ""
    if PRE_DROP.search(d) and not re.search(r"open offer", f"{d} {text}", re.I):
        return "Other", 0     # routine shareholding and query paperwork, not news
    for cat, tier, rx in FILING_RULES:
        if rx.search(d):
            if cat == "Management" and not SENIOR.search(f"{d} {text}"):
                return cat, 1
            if cat == "Ratings" and re.search(r"downgrad|withdraw|default", text, re.I):
                return cat, 3
            if cat == "Results" and "board" in d.lower() and not re.search(r"result|dividend|fund|raise|issue|acqui|merger|buy-?back|split|bonus|approv", text, re.I):
                return cat, 1     # a board meeting outcome that says nothing about results or money
            return cat, tier
    if DROP_DESC.search(d):
        return "Other", 0
    m = MATERIAL.search(f"{d} {text}")
    if m:
        for cat, tier, rx in FILING_RULES:
            if rx.search(text):
                return cat, min(tier, 2)
        return "Business Updates", 2
    return "Other", 0


PRESS_RULES = [
    ("Legal & Regulatory", r"\bsebi\b|\bed\b|raid|probe|penalt|fine[sd]?\b|court|tribunal|\bnclt\b|notice|insolven|arrest|fraud|investigation|\bcbi\b|show[- ]cause|tax demand|gst demand"),
    ("Deals & M&A", r"acqui|merger|demerger|takeover|open offer|buys?\b.*stake|sells?\b.*stake|stake sale|divest|joint venture|\bjv\b|delist|block deal|bulk deal|slump sale"),
    ("Orders & Contracts", r"\border(?:s)?\b.*(?:worth|crore|bag|win|secur)|bags?\b|wins?\b.*(?:order|contract)|secures?\b.*(?:order|contract)|contract\b"),
    ("Payouts & Buybacks", r"dividend|buy-?back|bonus (?:issue|share)|stock split|record date"),
    ("Capital Raising", r"\bqip\b|rights issue|fund ?rais|raises?\b.*(?:crore|₹|rs\b|billion|debt|bonds?|ncd)|preferential|\bfpo\b|\bofs\b|offer for sale|ncds?\b|bonds?\b"),
    ("Results", r"\bq[1-4] ?(?:fy)?\d*\b|quarterly|net profit|net loss|\bprofit\b|revenue|ebitda|results\b|earnings|margin"),
    ("Ratings", r"target price|price target|brokerage|downgrade|upgrade|rating|initiates coverage|overweight|underweight|outperform|\bbuy\b|\bsell\b|\bhold\b"),
    ("Management", r"\bceo\b|\bmd\b|\bcfo\b|chairman|resign|appoint|steps down|quits|successor|promoter"),
    ("Operations & Risk", r"\bfire\b|shutdown|shut down|strike\b|recall|outage|cyber ?(?:attack|incident|security incident)|data breach|\bdefault|halts? (?:production|operations)|disruption"),
    ("Business Updates", r"launch|unveil|\bdeal\b|signs?\b|agreement|pact|partner|tie[- ]?up|capex|capacity|expansion|new plant|approval|\busfda\b|\bfda\b|roll(?:s)? out|opens?\b"),
    ("Market Alerts", r"shares? (?:jump|surge|rally|slump|fall|tumble|plunge|soar|hit|zoom|gain)|stock (?:jump|surge|rally|slump|fall|tumble|plunge|soar|hit|zoom)|52-week|upper circuit|lower circuit|volume"),
]
PRESS_RULES = [(c, re.compile(p, re.I)) for c, p in PRESS_RULES]
PRESS_MAJOR = {"Legal & Regulatory", "Deals & M&A", "Payouts & Buybacks", "Capital Raising", "Operations & Risk"}
# corporate signal a press headline must carry before it counts as company news for a company outside the Nifty 100
CORPORATE = re.compile(
    r"\bshares?\b|\bstock\b|profit|loss\b|revenue|\border\b|acqui|merger|stake|dividend|buy-?back|\bq[1-4]\b|results|\bqip\b|rating|"
    r"target price|block deal|fund ?rais|\bceo\b|\bmd\b|chairman|resign|fraud|probe|penalt|default|insolven|\bnclt\b|delist|open offer|"
    r"plant|capacity|capex|expansion|contract|launch|listing|\bipo\b|\bsebi\b|\bed\b|raid|shutdown|recall|\busfda\b", re.I)
# international companies and world news that the Indian business feeds also carry
FOREIGN = re.compile(r"berkshire|buffett|tesla|\bapple\b|nvidia|microsoft|alphabet|google|amazon|meta platforms|openai|anthropic|samsung|toyota|"
                     r"volkswagen|boeing|\bintel\b|wall street|\bu\.?s\.?\b|\bus\b|trump|china|chinese|europe|\buk\b|japan|federal reserve|"
                     r"\bfed\b|pakistan|russia|ukraine|israel|iran|saudi", re.I)
# headlines that are about the market or the economy, not about one company
MARKET_NOISE = re.compile(
    r"sensex|nifty|stocks? to (?:buy|watch|sell)|market (?:wrap|outlook|live|today|update|close)|top (?:gainers|losers)|rupee|gold (?:price|rate)|"
    r"silver (?:price|rate)|crude|dollar|fii|dii|gift nifty|bank nifty|f&o|option chain|opening bell|closing bell|share price today|"
    r"stock price today|horoscope|gmp\b|grey market|live updates|technical (?:view|picks|outlook)|buy or sell|things to know|what to expect|"
    r"prize\b|scholarship|fixtures|bank holiday|\bholiday\b|share price highlights|stock price history|price history|bronstein|pomerantz|rosen law|levi & korsinsky|faruqi|gross law|kessler topaz|glancy|class action|"
    r"investors? who (?:lost|suffered)|stock market holiday|market holiday|ipo (?:allotment|status|listing date|subscription)|sponsored|advertorial|quiz|photos?:", re.I)


def classify_press(title):
    for cat, rx in PRESS_RULES:
        if rx.search(title):
            return cat
    return "Company News"


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def trim(s, n):
    s = clean(s)
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + " ..."


def http_get(url, headers=None, opener=None, tries=3, raw=False):
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
            with (opener.open(req, timeout=45) if opener else urllib.request.urlopen(req, timeout=45)) as r:
                data = r.read()
                return data if raw else data.decode("utf-8-sig", "replace")   # raw bytes let the XML parser honour the feed's own encoding
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (k + 1))
    raise last


# ---------------------------------------------------------------- Nifty 100 list
def load_nifty():
    cached = json.loads(N100.read_text(encoding="utf-8")) if N100.exists() else {"companies": []}
    for u in NIFTY_URLS:
        try:
            rows = list(csv.DictReader(io.StringIO(http_get(u))))
            cos = [{"name": r["Company Name"].strip(), "symbol": r["Symbol"].strip(), "industry": r["Industry"].strip(),
                    "isin": r["ISIN Code"].strip()} for r in rows if r.get("Symbol")]
            if len(cos) >= 90:
                N100.write_text(json.dumps({"updated": datetime.now(IST).strftime("%Y-%m-%d"), "companies": cos},
                                           ensure_ascii=False, indent=1), encoding="utf-8")
                return cos
        except Exception as e:  # noqa: BLE001
            print(f"  nifty list {u} failed: {e}", file=sys.stderr)
    print("  using cached Nifty 100 list", file=sys.stderr)
    return cached["companies"]


def build_matchers(cos):
    """[(symbol, compiled regex)] for spotting a Nifty 100 company in a headline."""
    out = []
    for c in cos:
        sym = c["symbol"]
        if sym in MANUAL:
            pat = MANUAL[sym]
        else:
            base = re.sub(r"\s+", " ", SUFFIX.sub("", c["name"]).replace("(India)", "").replace("of India", "")).strip(" .")
            base = re.sub(r"\s+India$", "", base).strip()
            forms = {re.escape(base)}
            first = base.split(" ")[0]
            if len(first) >= 5 and first not in STOP_FIRST and first.isalpha():
                forms.add(r"\b" + re.escape(first) + r"\b")
            pat = "|".join(sorted(forms, key=len, reverse=True))
        out.append((sym, re.compile(pat)))
    return out


def find_companies(text, matchers):
    """Symbols mentioned in text; a match inside a longer match of another company is ignored."""
    spans = []
    for sym, rx in matchers:
        for m in rx.finditer(text):
            spans.append((m.start(), m.end(), sym))
    keep = []
    for a in spans:
        if not any(b is not a and b[0] <= a[0] and a[1] <= b[1] and (b[1] - b[0]) > (a[1] - a[0]) for b in spans):
            keep.append(a)
    keep.sort()
    seen, order = set(), []
    for _, _, s in keep:
        if s not in seen:
            seen.add(s)
            order.append(s)
    return order


# ---------------------------------------------------------------- exchange filings
def nse_opener():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", UA), ("Accept", "application/json,text/plain,*/*"), ("Accept-Language", "en-US,en;q=0.9"),
                     ("Referer", "https://www.nseindia.com/companies-listing/corporate-filings-announcements")]
    try:
        op.open("https://www.nseindia.com/", timeout=30).read(500)
    except Exception as e:  # noqa: BLE001
        print(f"  nse handshake failed: {e}", file=sys.stderr)
    return op


def nse_filings(days, by_sym):
    op = nse_opener()
    out, today = [], datetime.now(IST).date()
    for k in range(days):
        d = today - timedelta(days=k)
        s = d.strftime("%d-%m-%Y")
        url = f"https://www.nseindia.com/api/corporate-announcements?index=equities&from_date={s}&to_date={s}"
        rows = None
        for attempt in range(3):
            try:
                rows = json.loads(http_get(url, opener=op, tries=1))
                break
            except Exception as e:  # noqa: BLE001
                print(f"  nse {s} attempt {attempt + 1} failed: {e}", file=sys.stderr)
                time.sleep(2)
                op = nse_opener()
        if rows is None:
            continue
        if isinstance(rows, dict):
            rows = rows.get("data", [])
        for r in rows:
            sym = (r.get("symbol") or "").strip()
            text = clean(r.get("attchmntText"))
            desc = clean(r.get("desc"))
            cat, tier = classify_filing(desc, text)
            n = by_sym.get(sym)
            if tier < (1 if (n and cat == "Management") else 2):
                continue
            sd = r.get("sort_date") or ""
            head = filing_head(desc, text, cat in ("Business Updates", "Deals & M&A", "Orders & Contracts"))
            out.append({"id": f"nse-{r.get('seq_id')}", "kind": "Exchange filing", "source": "NSE",
                        "universe": "nifty100" if n else "other", "symbol": sym, "company": clean(r.get("sm_name")) or sym,
                        "industry": n["industry"] if n else "", "category": cat, "major": tier >= 3,
                        "title": f"{clean(r.get('sm_name')) or sym}: {head}", "summary": trim(text, 420),
                        "date": sd[:10], "time": sd[11:16], "url": r.get("attchmntFile") or "https://www.nseindia.com/companies-listing/corporate-filings-announcements"})
        print(f"  nse {s}: {len(rows)} filings")
        time.sleep(0.8)
    return out


def bse_filings(days, nifty_norms, nse_norms):
    out, today = [], datetime.now(IST).date()
    hdr = {"Referer": "https://www.bseindia.com/corporates/ann.html", "Origin": "https://www.bseindia.com", "Accept": "application/json"}
    for k in range(days):
        d = (today - timedelta(days=k)).strftime("%Y%m%d")
        total = 0
        for page in range(1, BSE_MAX_PAGES + 1):
            url = ("https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?"
                   f"pageno={page}&strCat=-1&strPrevDate={d}&strScrip=&strSearch=P&strToDate={d}&strType=C&subcategory=-1")
            try:
                rows = json.loads(http_get(url, headers=hdr, tries=2)).get("Table") or []
            except Exception as e:  # noqa: BLE001
                print(f"  bse {d} page {page} failed: {e}", file=sys.stderr)
                break
            if not rows:
                break
            total += len(rows)
            for r in rows:
                name = clean(r.get("SLONGNAME"))
                nk = norm(name)
                if not name or nk in nifty_norms or nk in nse_norms:
                    continue      # on NSE (or in the Nifty 100): the NSE filing already covers it
                desc = clean(r.get("SUBCATNAME")) or clean(r.get("CATEGORYNAME"))
                text = clean(r.get("MORE")) or clean(r.get("HEADLINE"))
                text = re.sub(r"^dear sir/?ma'?'?am,?\s*", "", text, flags=re.I)
                cat, tier = classify_filing(desc, f"{text} {clean(r.get('NEWSSUB'))}")
                if tier < 2:
                    continue
                att = r.get("ATTACHMENTNAME") or ""
                nd = (r.get("NEWS_DT") or "")
                out.append({"id": f"bse-{r.get('NEWSID')}", "kind": "Exchange filing", "source": "BSE", "universe": "other",
                            "symbol": str(r.get("SCRIP_CD") or ""), "company": name, "industry": "", "category": cat, "major": tier >= 3,
                            "title": f"{name}: {filing_head(desc, text, True)}", "summary": trim(text, 420), "date": nd[:10], "time": nd[11:16],
                            "url": f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{att}" if att else (r.get("NSURL") or "https://www.bseindia.com/corporates/ann.html")})
            if len(rows) < 50:
                break
            time.sleep(0.4)
        print(f"  bse {d}: {total} filings read")
    return out


# ---------------------------------------------------------------- press
def press_items(matchers, by_sym, cutoff):
    out, now_ist = [], datetime.now(IST)
    for outlet, url in FEEDS:
        try:
            root = ET.fromstring(http_get(url, raw=True))
        except Exception as e:  # noqa: BLE001
            print(f"  feed {outlet} failed: {e}", file=sys.stderr)
            continue
        for it in root.iter("item"):
            title = clean(it.findtext("title"))
            link = (it.findtext("link") or "").strip()
            blurb = clean(it.findtext("description"))
            try:
                dt = parsedate_to_datetime(it.findtext("pubDate")).astimezone(IST)
            except Exception:  # noqa: BLE001
                dt = now_ist
            if not title or not link or dt.strftime("%Y-%m-%d") < cutoff or MARKET_NOISE.search(title):
                continue
            out.append(_press(outlet, title, blurb, link, dt, matchers, by_sym, google=False))
    return [x for x in out if x]


def _press(outlet, title, blurb, link, dt, matchers, by_sym, google):
    syms = find_companies(title, matchers)      # headline only: a company named in the blurb is often just a passing mention
    cat = classify_press(title)
    if syms:
        n = by_sym[syms[0]]
        uni, company, sym, ind = "nifty100", n["name"].replace(" Ltd.", "").replace(" Ltd", ""), syms[0], n["industry"]
    else:
        if google or not CORPORATE.search(title) or cat == "Company News" or FOREIGN.search(title):
            return None
        uni, company, sym, ind = "other", "", "", ""
    return {"id": "pr-" + norm(title)[:80], "kind": "Press", "source": outlet, "universe": uni, "symbol": sym, "company": company,
            "industry": ind, "category": cat, "major": cat in PRESS_MAJOR, "title": title, "summary": trim(blurb, 320),
            "date": dt.strftime("%Y-%m-%d"), "time": dt.strftime("%H:%M"), "url": link,
            "also": [c["name"] for c in (by_sym[s] for s in syms[1:4])] if syms else []}


GN_NOISE = re.compile(MARKET_NOISE.pattern + r"|share price|stock price|stocks? (?:in focus|to)|shares? (?:in focus|today)|"
                      r"target price|price target|technical|chart|support and resistance|should you|is it a buy|multibagger", re.I)
GN_BLOCK = re.compile(r"globenewswire|tipranks|whalesbook|kalkine|ad hoc news|newsip|tickertape|marketsmojo|scanx|stockinsights|moneycontrol\.com/live|trendlyne|equitypandit|"
                      r"stocktwits|investing\.com|simplywall|marketscreener|zeebiz live|dailyhunt|msn", re.I)


def google_news(cos, by_sym, matchers, cutoff):
    out = []
    for c in cos:
        name = SUFFIX.sub("", c["name"]).replace("(India)", "").replace(".", "").strip()
        q = urllib.parse.quote(f'"{name}" when:2d')
        url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
        try:
            root = ET.fromstring(http_get(url, tries=2, raw=True))
        except Exception as e:  # noqa: BLE001
            print(f"  google news {c['symbol']} failed: {e}", file=sys.stderr)
            continue
        got = 0
        for it in root.iter("item"):
            raw = clean(it.findtext("title"))
            src_el = it.find("source")
            source = clean(src_el.text) if src_el is not None and src_el.text else ""
            title = re.sub(r"\s+-\s+" + re.escape(source) + r"$", "", raw) if source else raw
            if not source and " - " in raw:
                title, source = raw.rsplit(" - ", 1)
            if not title or GN_NOISE.search(title) or GN_BLOCK.search(source):
                continue
            syms = find_companies(title, matchers)
            if c["symbol"] not in syms:
                continue        # the search returned it but the headline is about something else
            try:
                dt = parsedate_to_datetime(it.findtext("pubDate")).astimezone(IST)
            except Exception:  # noqa: BLE001
                continue
            if dt.strftime("%Y-%m-%d") < cutoff:
                continue
            cat = classify_press(title)
            out.append({"id": "pr-" + norm(title)[:80], "kind": "Press", "source": source or "Google News", "universe": "nifty100",
                        "symbol": c["symbol"], "company": c["name"].replace(" Ltd.", "").replace(" Ltd", ""), "industry": c["industry"],
                        "category": cat, "major": cat in PRESS_MAJOR, "title": title, "summary": "",
                        "date": dt.strftime("%Y-%m-%d"), "time": dt.strftime("%H:%M"), "url": (it.findtext("link") or "").strip(), "also": []})
            got += 1
            if got >= 5:
                break
        time.sleep(0.6)
    return out


# ---------------------------------------------------------------- main
def main():
    days = FILING_DAYS
    if "--backfill" in sys.argv:
        days = int(sys.argv[sys.argv.index("--backfill") + 1])
    now = datetime.now(IST)
    stamp = now.strftime("%Y-%m-%d %H:%M IST")
    cutoff = (now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    press_cutoff = (now - timedelta(days=3)).strftime("%Y-%m-%d")

    cos = load_nifty()
    by_sym = {c["symbol"]: c for c in cos}
    nifty_norms = {norm(c["name"]) for c in cos}
    matchers = build_matchers(cos)
    print(f"{len(cos)} Nifty 100 companies")

    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"items": []}
    known = {i["id"] for i in old["items"]}
    # a company can enter or leave the Nifty 100: re-tag stored items against today's list
    for i in old["items"]:
        n = by_sym.get(i.get("symbol")) if i["source"] == "NSE" else None
        if i["source"] == "NSE":
            i["universe"], i["industry"] = ("nifty100", n["industry"]) if n else ("other", "")

    found = nse_filings(days, by_sym)
    nse_norms = {norm(i["company"]) for i in found} | {norm(i["company"]) for i in old["items"] if i["source"] == "NSE"}
    found += bse_filings(days, nifty_norms, nse_norms)
    found += press_items(matchers, by_sym, press_cutoff)
    found += google_news(cos, by_sym, matchers, press_cutoff)

    seen_title, fresh = set(), []
    for it in sorted(found, key=lambda x: (x["kind"] != "Exchange filing", x["date"] + x.get("time", "")), reverse=False):
        key = norm(it["title"])[:90] if it["kind"] == "Press" else it["id"]
        if it["id"] in known or key in seen_title:
            continue
        seen_title.add(key)
        it["first_seen"] = stamp
        fresh.append(it)
    # outside the Nifty 100, keep at most a few items per company per day so one busy filer cannot flood the desk
    count, capped = {}, []
    for it in sorted(fresh, key=lambda x: (not x["major"], x["date"]), reverse=False):
        if it["universe"] == "other" and it["company"]:
            k = (norm(it["company"]), it["date"])
            count[k] = count.get(k, 0) + 1
            if count[k] > MAX_OTHER_PER_CO_DAY:
                continue
        capped.append(it)
    print(f"{len(capped)} new listed-company items "
          f"({sum(1 for i in capped if i['universe'] == 'nifty100')} Nifty 100, {sum(1 for i in capped if i['universe'] == 'other')} other)")

    items = [i for i in capped + old["items"] if i["date"] >= cutoff]
    items.sort(key=lambda i: (i["date"], i.get("time", ""), i["major"]), reverse=True)
    items = items[:MAX_ITEMS]
    OUT.write_text(json.dumps({"updated": stamp, "count": len(items), "items": items}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
