"""Investment Advisory Universe: the news -> data/advisory.json.

Python standard library only, no API keys, no AI. Nothing is summarised or interpreted: every card is a publisher's
headline plus the publisher's own blurb, with a link to the original. There is no commentary in this desk.
    python scripts/fetch_advisory.py

Sources
  RSS feeds: Economic Times (markets, stocks, mutual funds, commodities, bonds), Mint, Business Standard,
             BusinessLine, CNBC-TV18, CNBC, BBC Business, MarketWatch, Investing.com
  Google News searches for PMS, AIF, NCD / bonds / credit ratings, gold and silver, REITs / InvITs, mutual funds,
             regulators and global macro (the publisher is shown on every card)
  Official: SEBI and RBI items, plus Finance / Corporate Affairs ministry releases, copied from the Policy desk file
            (data/items.json) so the two desks never disagree.

Each item is sorted into ONE category by the first rule that matches (PMS, AIF, REITs & InvITs, Debt & Bonds,
Gold & Silver, Mutual Funds, Regulatory, Global, Equity Markets) and tagged with a sector when the headline names one.
Edit the tables below to change what is caught.
"""
import hashlib, html, json, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "advisory.json"
IST = timezone(timedelta(hours=5, minutes=30))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
KEEP_DAYS = 60
FIRST_FILL_DAYS = 14
MAX_ITEMS = 3000

# (outlet, url, default category or None = decide by rules, scope) scope "in" = India markets feed, "gl" = global feed
FEEDS = [
    ("Economic Times", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", "Equity Markets"),
    ("Economic Times", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms", "Equity Markets"),
    ("Economic Times", "https://economictimes.indiatimes.com/mf/rssfeeds/359241701.cms", "Mutual Funds"),
    ("Economic Times", "https://economictimes.indiatimes.com/markets/commodities/rssfeeds/1808152121.cms", None),
    ("Economic Times", "https://economictimes.indiatimes.com/markets/bonds/rssfeeds/2146843.cms", "Debt & Bonds"),
    ("Mint", "https://www.livemint.com/rss/markets", "Equity Markets"),
    ("Mint", "https://www.livemint.com/rss/money", None),
    ("Business Standard", "https://www.business-standard.com/rss/markets-106.rss", "Equity Markets"),
    ("Business Standard", "https://www.business-standard.com/rss/finance-103.rss", None),
    ("Business Standard", "https://www.business-standard.com/rss/economy-102.rss", None),
    ("BusinessLine", "https://www.thehindubusinessline.com/markets/feeder/default.rss", "Equity Markets"),
    ("BusinessLine", "https://www.thehindubusinessline.com/markets/stock-markets/feeder/default.rss", "Equity Markets"),
    ("BusinessLine", "https://www.thehindubusinessline.com/money-and-banking/feeder/default.rss", None),
    ("BusinessLine", "https://www.thehindubusinessline.com/portfolio/feeder/default.rss", None),
    ("CNBC-TV18", "https://www.cnbctv18.com/commonfeeds/v1/cne/rss/market.xml", "Equity Markets"),
    ("CNBC", "https://www.cnbc.com/id/10000664/device/rss/rss.html", "Global"),
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml", "Global"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories", "Global"),
    ("Investing.com", "https://www.investing.com/rss/news_25.rss", "Global"),
]
# Google News searches: (query, category used when the headline rules find nothing)
SEARCHES = [
    ("PMS portfolio management services India", "PMS"), ("PMS AUM India fund manager", "PMS"), ("portfolio manager SEBI PMS", "PMS"),
    ("PMS strategy returns India", "PMS"), ("APMI PMS data", "PMS"),
    ("AIF category III India", "AIF"), ("alternative investment fund India launch", "AIF"), ("SEBI AIF rules", "AIF"),
    ("Category II AIF fund close India", "AIF"), ("angel fund SEBI AIF", "AIF"),
    ("NCD public issue India", "Debt & Bonds"), ("NCD issue opens coupon rating", "Debt & Bonds"),
    ("corporate bond India yield spread", "Debt & Bonds"), ("credit rating downgrade India CRISIL ICRA", "Debt & Bonds"),
    ("credit rating upgrade India CARE India Ratings", "Debt & Bonds"), ("India 10-year G-Sec yield", "Debt & Bonds"),
    ("RBI bond auction government securities", "Debt & Bonds"), ("bond default India debenture", "Debt & Bonds"),
    ("gold price India MCX", "Gold & Silver"), ("silver price India MCX", "Gold & Silver"), ("gold ETF SEBI India", "Gold & Silver"),
    ("sovereign gold bond RBI", "Gold & Silver"), ("gold silver global prices central banks", "Gold & Silver"),
    ("REIT India units", "REITs & InvITs"), ("InvIT India", "REITs & InvITs"), ("REIT InvIT SEBI", "REITs & InvITs"),
    ("mutual fund NFO India", "Mutual Funds"), ("AMFI SIP inflows", "Mutual Funds"), ("mutual fund SEBI new rules", "Mutual Funds"),
    ("SEBI circular investors", "Regulatory"), ("SEBI board meeting decisions", "Regulatory"), ("RBI monetary policy repo rate", "Regulatory"),
    ("RBI circular banks NBFC", "Regulatory"), ("AMFI regulatory mutual fund", "Regulatory"),
    ("Federal Reserve interest rate decision", "Global"), ("crude oil price OPEC Brent", "Global"), ("US Treasury yields dollar", "Global"),
    ("emerging markets FPI flows India", "Global"), ("global stock markets Asia Europe", "Global"), ("China economy stimulus markets", "Global"),
    ("sectors outperform Nifty top sector", "Equity Markets"), ("Nifty Sensex closing market wrap", "Equity Markets"),
    ("FII DII flows India market", "Equity Markets"), ("IPO market India SME mainboard", "Equity Markets"),
]

# category rules, first match on headline + blurb wins
CATEGORY_RULES = [
    ("PMS", re.compile(r"\bPMS\b|portfolio management (?:service|scheme)|portfolio manager", re.I)),
    ("AIF", re.compile(r"\bAIFs?\b|alternative investment fund|category (?:I|II|III)\b|cat[- ](?:I|II|III)\b|angel fund|venture capital fund", re.I)),
    ("REITs & InvITs", re.compile(r"\bREITs?\b|\bInvITs?\b|real estate investment trust|infrastructure investment trust", re.I)),
    ("Gold & Silver", re.compile(r"\bgold\b|\bsilver\b|bullion|sovereign gold|\bSGBs?\b|gold ETF|silver ETF|precious metal", re.I)),
    ("Debt & Bonds", re.compile(r"\bNCDs?\b|non-convertible|debentures?|\bbonds?\b|g-?sec|gilts?|bond yield|10-year (?:yield|bond|g-?sec)|"
                                r"credit rating|rating (?:upgrade|downgrade|action|reaffirm)|\bCRISIL\b|\bICRA\b|CARE Ratings|India Ratings|Acuite|"
                                r"corporate debt|\bT-bills?\b|sukuk|commercial paper|tier[- ]?[12] bonds|\bAT1\b|call money|liquidity (?:deficit|surplus)|repo auction", re.I)),
    ("Mutual Funds", re.compile(r"mutual funds?|\bNFOs?\b|\bSIPs?\b|\bAMFI\b|fund house|\bAMCs?\b|\bETFs?\b|index funds?|flexi-?cap fund|mid-?cap fund|small-?cap fund", re.I)),
    ("Regulatory", re.compile(r"\bSEBI\b|\bRBI\b|reserve bank|\bIRDAI\b|\bPFRDA\b|\bCBDT\b|master direction|master circular|\bcircular\b|consultation paper|"
                              r"repo rate|monetary policy|\bMPC\b|\bCRR\b|\bSLR\b|capital gains tax|\bSTT\b|\bFPI\b rules|insider trading|\bLODR\b", re.I)),
    ("Global", re.compile(r"\bFed\b|federal reserve|\bFOMC\b|\bECB\b|bank of japan|\bBoJ\b|bank of england|\bOPEC\b|brent|crude|wall street|s&p 500|"
                          r"nasdaq|dow jones|tariffs?|\bchina\b|\biran\b|russia|ukraine|treasury yields|dollar index|global markets|asian markets|european markets|"
                          r"\bIMF\b|world bank|emerging markets?|hang seng|nikkei|middle east|trump|geopolit", re.I)),
]
INDIA_HINT = re.compile(r"\bindia\b|indian|\brupee\b|\bINR\b|nifty|sensex|\bsebi\b|\brbi\b|\bNSE\b|\bBSE\b|\bcrore\b|\blakh\b|₹|\bRs\.?\s?\d", re.I)
SECTORS = [
    ("IT & Tech", r"\bIT (?:stocks?|sector|services|index)|nifty it\b|infosys|\btcs\b|wipro|hcltech|tech mahindra|software|\bAI\b|semiconductor"),
    ("Banks & Financials", r"\bbanks?\b|banking|nifty bank|\bNBFCs?\b|hdfc bank|icici bank|sbi\b|kotak|axis bank|lender|insurance|financials?"),
    ("Pharma & Healthcare", r"pharma|healthcare|hospital|drug|biotech|sun pharma|cipla|dr reddy|apollo"),
    ("FMCG & Consumption", r"fmcg|consumer|consumption|hindustan unilever|\bITC\b|nestle|britannia|retail|jewel"),
    ("Auto", r"\bauto(?:mobile)?s?\b|\bEVs?\b|maruti|tata motors|mahindra|two-wheeler|bajaj auto|hero motocorp"),
    ("Metals & Mining", r"\bmetals?\b|steel|aluminium|copper|zinc|mining|tata steel|jsw|vedanta|hindalco|coal"),
    ("Realty & Infra", r"realty|real estate|housing|infrastructure|\binfra\b|construction|cement|l&t|larsen"),
    ("Energy & Power", r"\boil\b|\bgas\b|energy|power|renewable|solar|reliance|ongc|ntpc|adani green|coal india"),
    ("PSU", r"\bPSUs?\b|public sector|psu bank|disinvest"),
    ("Telecom & Media", r"telecom|airtel|\bjio\b|vodafone|media|entertainment"),
    ("Chemicals & Materials", r"chemicals?|fertili[sz]er|specialty chem"),
    ("Defence & Capital Goods", r"defence|defense|capital goods|railway|shipbuild|\bHAL\b|bel\b|bhel"),
]
SECTORS = [(n, re.compile(p, re.I)) for n, p in SECTORS]
NOISE = re.compile(r"horoscope|astrology|zodiac|fantasy|dream11|lottery|recipe|cricket|bollywood|celebrity|wedding|movie|box office|"
                   r"sponsored|advertorial|photos?:|webinar|quiz\b|podcast|newsletter|coupon code|stock tips? for today|buy or sell:|"
                   r"intraday picks?|stocks to buy today|sunday special|panchang|rashifal|"
                   r"^what (?:are|is)|^how (?:do|does|to)|explained|explainer|guide to|everything you need|meaning of|"
                   r"alm reporting|submits? .{0,40} to (?:rbi|sebi)|hosts? (?:an? )?(?:important |national )?(?:session|workshop|conference)|"
                   r"epidemiolog|public health", re.I)
OFFTOPIC = re.compile(r"real madrid|premier league|nfl\b|nba\b|world cup|fashion week|taylor swift|kardashian", re.I)


def get(url, timeout=30, tries=2):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read().decode("utf-8-sig", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5)
    raise last


def txt(s):
    s = re.sub(r"<!\[CDATA\[|\]\]>", "", s or "")
    s = re.sub(r"<(script|style|figure|figcaption).*?</\1>", " ", s, flags=re.S | re.I)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s)).replace("\xa0", " ")).strip()


def clip(s, n=300):
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + " ..."


def when(item):
    for tag in ("pubDate", "{http://purl.org/dc/elements/1.1/}date", "published"):
        raw = txt(item.findtext(tag) or "")
        if raw:
            try:
                return parsedate_to_datetime(raw).astimezone(IST)
            except Exception:  # noqa: BLE001
                try:
                    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(IST)
                except Exception:  # noqa: BLE001
                    pass
    return None


MARKET_LEVEL = re.compile(r"sensex|nifty|market|sector|index|indices|FII|DII|FPI|foreign (?:investors|institutional)|IPO|stocks to watch|rally|sell-?off|"
                          r"gainers|losers|mid-?cap|small-?cap|breadth|volatility|VIX|rupee|earnings season|dalal street|bull|bear|correction", re.I)
STOCK_HEAVY = {"https://www.cnbctv18.com/commonfeeds/v1/cne/rss/market.xml", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
               "https://www.thehindubusinessline.com/markets/stock-markets/feeder/default.rss"}


def categorise(title, blurb, default, strict=False):
    hay = f"{title} {blurb}"
    for cat, rx in CATEGORY_RULES:
        if rx.search(title) or (cat in ("PMS", "AIF", "REITs & InvITs") and rx.search(hay)):
            return cat
    for cat, rx in CATEGORY_RULES:
        if cat in ("PMS", "AIF", "REITs & InvITs") and rx.search(hay):
            return cat
    if strict and default not in ("Equity Markets", "Global"):
        return None          # a search for a specific product only counts when the headline is really about it
    return default


def sector_of(title, blurb):
    return next((n for n, rx in SECTORS if rx.search(title)), None)


def uid(url):
    return "ad-" + hashlib.md5(url.encode()).hexdigest()[:14]


def collect_feed(outlet, url, default, cutoff, out):
    try:
        root = ET.fromstring(get(url).lstrip("﻿"))
    except Exception as e:  # noqa: BLE001
        print(f"  {outlet} feed failed ({url.rsplit('/', 2)[-2]}): {e}", file=sys.stderr)
        return
    n = 0
    for it in root.iter("item"):
        title = txt(it.findtext("title"))
        link = (it.findtext("link") or "").strip()
        dt = when(it)
        if not title or not link or not dt or dt < cutoff or NOISE.search(title) or OFFTOPIC.search(title):
            continue
        blurb = clip(txt(it.findtext("description") or it.findtext("{http://purl.org/rss/1.0/modules/content/}encoded") or ""))
        if blurb.lower().startswith(title.lower()[:40]):
            blurb = ""
        if url in STOCK_HEAVY and not MARKET_LEVEL.search(title):
            continue          # single-company chatter is the Listed Universe desk's job; this desk is about markets and products
        cat = categorise(title, blurb, default)
        if not cat:
            continue
        if default == "Global" and cat == "Global" and INDIA_HINT.search(f"{title} {blurb}") is None and not re.search(r"fed\b|oil|crude|opec|treasury|tariff|china|dollar|ecb|inflation|rates?|gold|market", title, re.I):
            continue          # keep the Global desk about things that move money
        out.append({"id": uid(link), "title": title, "url": link, "source": outlet, "kind": "News", "category": cat,
                    "sector": sector_of(title, blurb) if cat in ("Equity Markets", "Global", "Regulatory", "Mutual Funds") else None,
                    "summary": blurb, "date": dt.strftime("%Y-%m-%d"), "time": dt.strftime("%H:%M")})
        n += 1
    print(f"  {outlet:18} {url.rsplit('/', 2)[-2][:28]:28} {n} items")


def collect_google(query, default, days, out):
    q = urllib.parse.quote_plus(f"{query} when:{days}d")
    try:
        root = ET.fromstring(get(f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en").lstrip("﻿"))
    except Exception as e:  # noqa: BLE001
        print(f"  google '{query}' failed: {e}", file=sys.stderr)
        return
    cutoff = datetime.now(IST) - timedelta(days=days + 1)
    n = 0
    for it in root.iter("item"):
        raw = txt(it.findtext("title"))
        link = (it.findtext("link") or "").strip()
        src = txt(it.findtext("source")) or "Google News"
        title = raw[: -len(src) - 3].strip() if raw.endswith(" - " + src) else raw
        dt = when(it)
        if not title or not link or not dt or dt < cutoff or NOISE.search(title) or OFFTOPIC.search(title):
            continue
        if default in ("PMS", "AIF", "Debt & Bonds", "Gold & Silver", "REITs & InvITs", "Mutual Funds", "Regulatory", "Equity Markets") and not INDIA_HINT.search(title) \
                and default not in ("Gold & Silver",) and not re.search(r"PMS|AIF|NCD|REIT|InvIT|SEBI|RBI|AMFI", title):
            continue
        cat = categorise(title, "", default, strict=True)
        if not cat:
            continue
        out.append({"id": uid(link), "title": title, "url": link, "source": src, "kind": "News", "category": cat,
                    "sector": sector_of(title, "") if cat in ("Equity Markets", "Global", "Regulatory", "Mutual Funds") else None,
                    "summary": "", "date": dt.strftime("%Y-%m-%d"), "time": dt.strftime("%H:%M")})
        n += 1
    print(f"  google {query[:44]:44} {n}")


def official_items(cutoff_date):
    """SEBI / RBI and finance-ministry items from the Policy desk file, shown here as 'Official' regulatory cards."""
    p = DATA / "items.json"
    if not p.exists():
        return []
    out = []
    for i in json.loads(p.read_text(encoding="utf-8"))["items"]:
        keep = i["source"] in ("RBI", "SEBI") or re.search(r"finance|economic affairs|revenue|corporate affairs|financial services", i.get("ministry", ""), re.I)
        if not keep or i["date"] < cutoff_date:
            continue
        out.append({"id": "ad-" + i["id"], "title": i["title"], "url": i["url"], "source": i["source"], "kind": "Official", "category": "Regulatory",
                    "sector": None, "summary": i.get("summary", ""), "date": i["date"], "time": "", "major": bool(i.get("major")), "ministry": i.get("ministry", "")})
    return out


def tokens(t):
    return {w.rstrip("s") for w in re.findall(r"[a-z0-9]+", t.lower()) if len(w) > 3}


def main():
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"items": []}
    first = not old["items"]
    now = datetime.now(IST)
    days = FIRST_FILL_DAYS if first else 4
    cutoff = now - timedelta(days=days)
    fresh = []
    print("RSS feeds")
    for outlet, url, default in FEEDS:
        collect_feed(outlet, url, default, cutoff, fresh)
    print("Google News searches")
    for q, default in SEARCHES:
        collect_google(q, default, days, fresh)
        time.sleep(0.6)
    fresh += official_items((now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d"))

    known = {i["id"] for i in old["items"]}
    urls = {i["url"] for i in old["items"]}
    stamp = now.strftime("%Y-%m-%d %H:%M IST")
    new = []
    seen_ids = set()
    for i in sorted(fresh, key=lambda x: (x["date"], x["time"]), reverse=True):
        if i["id"] in known or i["url"] in urls or i["id"] in seen_ids:
            continue
        seen_ids.add(i["id"])
        i["first_seen"] = stamp
        new.append(i)

    # the same story under another outlet's headline: keep the first, list the others as "also covered by"
    merged, pools = [], {}
    for i in new:
        t = tokens(i["title"])
        hit = None
        for m, mt in pools.get((i["category"], i["date"]), []):
            if t and mt and len(t & mt) / len(t | mt) >= 0.55:
                hit = m
                break
        if hit:
            hit.setdefault("also", []).append({"source": i["source"], "url": i["url"]})
            continue
        pools.setdefault((i["category"], i["date"]), []).append((i, t))
        merged.append(i)

    # official items already on file keep their flags fresh (a title can be edited by the regulator); everything else is append-only
    items = merged + old["items"]
    keep_from = (now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    items = [i for i in items if i["date"] >= keep_from]
    items = sorted(items, key=lambda i: (i["date"], i.get("time", ""), i["first_seen"]), reverse=True)[:MAX_ITEMS]
    counts = {}
    for i in items:
        counts[i["category"]] = counts.get(i["category"], 0) + 1
    print(f"{len(merged)} new items; {len(items)} on file; by category {counts}")
    if not merged and not first:
        OUT.write_text(json.dumps({**old, "updated": stamp}, ensure_ascii=False, indent=1), encoding="utf-8")
        return
    OUT.write_text(json.dumps({"updated": stamp, "count": len(items), "items": items}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
