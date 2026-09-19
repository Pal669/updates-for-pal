"""Collect startup news into data/startups.json.

Same rules as the Policy Desk: Python standard library only, no API keys, no AI service.
    python scripts/fetch_startups.py

Sources (public RSS feeds): Inc42, YourStory, Startup Story, Economic Times Startups (India),
TechCrunch Startups (global), MediaNama (tech policy touching startups).

For every story it keeps only what can be lifted reliably from the article text: deal amount, stage, investors,
and (when the article says "<City>-based startup ...") what the company does, plus any FY revenue/profit lines.
"How a startup makes money" is NOT guessed by rules. That lives in hand-written Startup Files (data/profiles.json).
"""
import html, json, re, sys, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "startups.json"
UA = {"User-Agent": "Mozilla/5.0 (updates-for-pal)"}
IST = timezone(timedelta(hours=5, minutes=30))
MAX_ITEMS = 1500
MAX_FETCH = 60          # article pages fetched per run (only for feeds that ship a short blurb)
KEEP_DAYS = 45          # ignore feed items older than this on first fill

FEEDS = [
    ("Inc42", "India", "https://inc42.com/feed/"),
    ("YourStory", "India", "https://yourstory.com/feed"),
    ("Startup Story", "India", "https://startupstorymedia.com/feed"),
    ("ET Startups", "India", "https://economictimes.indiatimes.com/tech/startups/rssfeeds/78570561.cms"),
    ("TechCrunch", "Global", "https://techcrunch.com/category/startups/feed/"),
    ("TechCrunch Venture", "Global", "https://techcrunch.com/category/venture/feed/"),
    ("Sifted", "Global", "https://sifted.eu/feed"),
    ("MediaNama", "India", "https://www.medianama.com/feed/"),
]

RELEVANT = re.compile(
    r"startup|start-up|funding|funded|raises?\b|raised|bags?\b|secures?|lands?\b.*(round|funding)|series [a-h]\b|seed|"
    r"pre-ipo|valuation|unicorn|soonicorn|decacorn|\bipo\b|drhp|acqui|merger|venture|\bvcs?\b|angel|accelerator|"
    r"founder|co-founder|layoff|lays off|shuts? down|winds? up|insolven|profit|loss(es)?\b|revenue|\barr\b|\bgmv\b|"
    r"d2c|fintech|edtech|healthtech|agritech|saas|quick commerce|neobank|new-age|scale-?up|bootstrapped|pivot", re.I)
DEDICATED = {"Inc42", "YourStory", "Startup Story"}
INDIA_ONLY = {"Inc42", "YourStory", "Startup Story"}      # these outlets cover Indian startups by definition
INDIA_MARK = re.compile(
    r"\bindia\b|\bindian\b|₹|\brs\.? ?\d|\bcrore\b|\blakh\b|\bcr\b|bengaluru|bangalore|mumbai|delhi|gurugram|gurgaon|"
    r"hyderabad|chennai|pune|kolkata|ahmedabad|jaipur|kochi|\bsebi\b|\brbi\b|\bupi\b|meity|dpiit|\bnse\b|\bbse\b", re.I)
STRICT = re.compile(
    r"startups?\b|start-up|raises?\b|raised|series [a-h]\b|pre-seed|seed (?:round|funding)|valuation|unicorn|soonicorn|"
    r"\bipo\b|drhp|acquires?|acquired|acquisition|founders?\b|layoffs?|d2c|saas|fintech|edtech|healthtech|agritech|"
    r"cloud kitchens?|quick commerce|venture (?:capital|debt)|\bvcs?\b|funding round|fundrais", re.I)
FINANCE = re.compile(r"fy ?2\d|ebitda|net (?:profit|loss)|profit|loss(?:es)?\b|revenue|new-age|market debut|shares|subscribed|anchor investors|listing|\bmdr\b|upi|unit economics", re.I)
NOISE = re.compile(
    r"books? for|self-growth|horoscope|\bquiz\b|podcast|how to |tips for|things to|listicle|newsletter|webinar|"
    r"quotes? (?:to|for)|exhibit|disrupt 2026|final \d+ hours|days left|semicon|semiconductor|chip |women powering|daily roundup|weekly funding roundup|sponsored|partner content|advertorial|giveaway|photos?:", re.I)

TYPES = [  # first match wins
    ("Shutdown & Layoffs", r"layoffs?|lays? off|shuts? down|shutting|winds? up|insolven|bankrupt|fire[sd]? |downsiz"),
    ("IPO & Listing", r"\bipo\b|drhp|listing|lists? on|listed|pre-ipo|public issue|nse|bse"),
    ("Acquisition", r"acqui|merger|merges?|buys?\b|takes over|buyout|stake sale|sells? stake"),
    ("Funding", r"raises?\b|raised|bags?\b|secures?|funding|series [a-h]\b|seed|round|invests?\b|investment|valuation|backed|infuse"),
    ("Financials", r"revenue|profit|loss|fy2\d|ebitda|turnover|\barr\b|\bgmv\b|narrows|widens|zooms|jumps"),
    ("Launch & Product", r"launch|unveil|introduc|rolls? out|debut|expands?\b|opens?\b"),
]
TYPES = [(l, re.compile(p, re.I)) for l, p in TYPES]

SECTORS = [
    ("Fintech", r"fintech|lending|nbfc|loan|credit|payments?|upi|neobank|insurtech|insurance|wealth|broking|bank|wallet|bnpl|mutual fund"),
    ("AI & Deeptech", r"\bai\b|artificial intelligence|genai|llm|agentic|robot|deeptech|semiconductor|quantum|space|satellite|drone|chip"),
    ("SaaS & Enterprise", r"saas|enterprise|b2b|cloud|software|cyber|devops|api\b|workflow|analytics"),
    ("Commerce & D2C", r"d2c|direct-to-consumer|e-?commerce|quick commerce|retail|marketplace|fashion|beauty|apparel|consumer brand|grocery|food delivery|restaurant|fmcg|foodtech"),
    ("Health & Wellness", r"health|medtech|pharma|diagnostic|hospital|wellness|fitness|fertility|biotech|clinic"),
    ("Edtech & Skills", r"edtech|education|learning|upskill|coaching|school|university"),
    ("Mobility & EV", r"\bev\b|electric vehicle|mobility|ride|auto|battery|charging|scooter|fleet"),
    ("Climate & Energy", r"climate|solar|renewable|clean energy|carbon|green hydrogen|energy storage|cleantech|waste"),
    ("Logistics & Supply Chain", r"logistic|supply chain|freight|warehouse|delivery|shipping|last-mile|trucking"),
    ("Agri & Food", r"agri|farm|food processing|dairy|crop|aqua|foodtech"),
    ("Real Estate & Workspaces", r"real estate|proptech|workspace|housing|coworking|rental|construction"),
    ("Media, Gaming & Creators", r"gaming|game|media|creator|entertainment|ott|music|streaming|social"),
    ("Policy & Regulation", r"trai|rbi|sebi|meity|regulat|bill\b|ban\b|policy|compliance|tax|dpdp"),
]
SECTORS = [(l, re.compile(p, re.I)) for l, p in SECTORS]

MODELS = [  # (tag, pattern) - a story can carry several
    ("Subscription / SaaS", r"saas|subscription|annual recurring|\barr\b|recurring revenue|per seat|licen[cs]ing fee"),
    ("Marketplace / commission", r"marketplace|commission|take rate|\bgmv\b|platform fee|convenience fee|per order"),
    ("Lending / interest income", r"nbfc|lending|loans?\b|net interest|\baum\b|credit line|interest income|disburs"),
    ("Product sales / D2C", r"d2c|direct-to-consumer|own brand|retail stores|private label|gross margin|manufactur|sells its|product sales"),
    ("Advertising", r"advertising|ad revenue|ad-supported|advertisers"),
    ("Payments & transaction fees", r"\bmdr\b|transaction fee|payment gateway|processing fee|interchange"),
    ("Insurance & broking", r"insurance premium|premiums|broking|brokerage|distribution income|policies sold|insurtech"),
    ("Services / contracts (B2B)", r"enterprise clients|b2b|contracts?\b|managed services|implementation|consulting"),
    ("Rentals / usage-based", r"rentals?|per hour|pay-per-use|usage-based|leasing|occupancy|per seat per month"),
]
MODELS = [(t, re.compile(p, re.I)) for t, p in MODELS]

VERBS = (r"raises?|raised|bags?|secures?|lands?|closes?|gets?|receives?|mops? up|scoops? up|nets?|garners?|"
         r"acquires?|acquired|buys?|sells?|launches?|unveils?|introduces?|files?|gets? sebi|crosses?|reports?|"
         r"turns?|posts?|clocks?|zooms?|jumps?|narrows?|widens?|slips?|drops?|shuts?|lays? off|eyes?|plans?|"
         r"targets?|hits?|becomes?|expands?|opens?|partners?|ties? up|signs?|appoints?|onboards?|is |are |to |"
         r"set to|says?|wins?|backs?|invests?|infuses?|rolls? out|aims?|looks?|seeks?|mulls?|pivots?|enters?")
NAME_RX = re.compile(r"^(?P<n>[A-Z0-9][\w&.'’\-]*(?: [A-Z0-9][\w&.'’\-]*){0,3}?)\s+(?:%s)" % VERBS)

MONEY = re.compile(r"(?:US\$|USD|\$|₹|Rs\.?|INR)\s?\d[\d,]*(?:\.\d+)?\s?(?:-\s?[\d.]+\s?)?(?:crore|cr\b|Cr\b|lakh|million|mn\b|Mn\b|m\b|M\b|billion|bn\b|Bn\b|b\b|B\b|k\b|K\b)?", re.I)
STAGE = re.compile(r"\b(pre-?seed|seed|pre-?series [a-h]|series [a-h]\d?|bridge round|growth round|pre-?ipo|debt funding|venture debt|angel round|grant)\b", re.I)
LED_BY = re.compile(r"(?:led by|backed by)\s+([A-Z][^.;]{3,140}?)(?:\.|;|, (?:with|which|to|the)|\band existing\b|$)")

WHAT = re.compile(
    r"\b(is|are|was)\s+(an?|the)\s+[^.]{0,110}?\b(platform|startup|start-up|company|firm|marketplace|app|provider|brand|maker|network|operator|"
    r"lender|bank|fintech|saas|studio|venture|business|service|player|manufacturer|developer|builder|chain|aggregator|solution|"
    r"space|arm|unit|nbfc)\b"
    r"|\b(builds?|operates?|offers?|provides?|sells?|helps?|enables?|runs?|develops?|makes?|manufactures?|delivers?|connects?|"
    r"lets?|allows?|specialis[e]s in|focus(es)? on|works? on)\b\s+[^.]{15,}", re.I)
MONEY_HOW = re.compile(
    r"\b(earns?|makes? money|generates?|revenue (?:comes|is (?:driven|derived|generated)|streams?)|derives?|monet[iz]|commission|take rate|"
    r"subscription|charges?|fees?\b|margins?|per (?:order|transaction|user|seat|month|hour|kg|unit)|business model|unit economics|"
    r"recurring|licen[cs]ing|revenue mix|contribution margin|sells? (?:its|to)|net interest|spread|pricing|priced at)\b", re.I)
FIN = re.compile(r"(?:\bFY ?2\d|Q[1-4] ?FY ?2\d|fiscal|financial year|for the (?:year|quarter))[^.]*?(?:revenue|income|profit|loss|ebitda|turnover)|"
                 r"(?:revenue|operating revenue|net loss|net profit|loss|profit|ebitda)[^.]{0,80}(?:₹|Rs|\$)\s?[\d,.]+", re.I)


# ---------------------------------------------------------------- helpers

def get(url):
    last = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45) as r:
                return r.read().decode("utf-8-sig", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
    raise last


def txt(s):
    s = re.sub(r"<!\[CDATA\[|\]\]>", "", s or "")
    s = re.sub(r"<(script|style|figure|figcaption|aside).*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"</(p|div|li|h\d)>|<br\s*/?>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"[ \t\xa0]+", " ", s).strip()


def one_line(s):
    return re.sub(r"\s+", " ", s).strip()


BOILER = re.compile(r"we may earn|purchase through|affiliate|all rights reserved|click here|sign up|subscribe|"
                    r"disclaimer|inc42 (?:has|is|plus)|our (?:newsletter|readers)|follow us|cookie|"
                    r"[“”\"]|\bsaid\b|\bsays\b|\btold\b|\badded\b|\bnoted\b", re.I)
BASED = re.compile(r"[A-Z][A-Za-z]+(?:-[A-Za-z]+)?-based\s+(?:[A-Za-z0-9&\-]+\s+){0,4}?"
                   r"(?:startup|start-up|company|firm|platform|fintech|saas|brand|marketplace|nbfc|maker|provider|operator|lender|venture|player|app)", re.I)


def sentences(body):
    out = []
    for para in body.split("\n"):
        para = one_line(para)
        if len(para) < 40 or re.match(r"^(read (also|more)|also read|the post |follow |subscribe|image credit|photo|source:|disclaimer)", para, re.I):
            continue
        out += [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z₹$\"“‘0-9])", para) if s.strip()]
    return out


def article_body(it, link):
    """Full text from content:encoded when the feed ships it; otherwise fetch the page (limited)."""
    enc = it.find("{http://purl.org/rss/1.0/modules/content/}encoded")
    if enc is not None and enc.text and len(enc.text) > 900:
        return txt(enc.text)
    return None


def fetch_page_body(url):
    try:
        page = get(url)
    except Exception:  # noqa: BLE001
        return ""
    m = re.search(r"<article.*?</article>", page, re.S | re.I)
    chunk = m.group(0) if m else page
    paras = re.findall(r"<p[^>]*>(.*?)</p>", chunk, re.S | re.I)
    return "\n".join(txt(p) for p in paras)


POSS = re.compile(r"^(?P<n>[A-Z0-9][\w&.\-]*(?: [A-Z0-9][\w&.\-]*){0,2})[’']s\b")


def company_name(title):
    t = re.sub(r"^\(.*?\)\s*", "", title.strip())
    pm = POSS.match(t)
    if pm:
        return pm.group("n")
    m = NAME_RX.match(t)
    if m:
        n = m.group("n").strip(" ,:-")
        if 1 <= len(n.split()) <= 4 and n.lower() not in {"the", "india", "indian", "how", "why", "what", "this", "these", "new"}:
            return n
    return None


def first(rx, s):
    m = rx.search(s)
    return m.group(0).strip() if m else None


def clip(s, n=330):
    s = one_line(s)
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + " ..."


def extract(title, blurb, body):
    text = body or blurb
    sents = sentences(text) if text else []
    head = f"{title}. {blurb}"

    what = None
    ok = [s for s in sents[:16] if 40 <= len(s) <= 320 and not BOILER.search(s)
          and not re.match(r"^(the|this) (round|funds?|deal|investment|capital|tender|company said)", s, re.I)]
    for rx in (BASED, WHAT):
        what = next((clip(s) for s in ok if rx.search(s)), None)
        if what:
            break
    how = [clip(s) for s in sents if MONEY_HOW.search(s) and len(s) >= 50 and not BOILER.search(s)
           and not re.search(r"^\W*(read|also)", s, re.I)]
    how = how[:2]
    fin = []
    for s in sents:
        if FIN.search(s) and re.search(r"\d", s):
            fin.append(clip(s, 260))
        if len(fin) == 2:
            break

    alltext = f"{head} {text[:6000]}"
    amount = first(MONEY, title) or first(MONEY, blurb) or None
    stage = first(STAGE, head)
    led = LED_BY.search(f"{title}. {blurb}. {text[:1500]}")
    investors = clip(led.group(1), 160) if led else None

    core = f"{head} {text[:3500]}"
    scored = [(len(rx.findall(core)) + 2 * len(rx.findall(head)), t) for t, rx in MODELS]
    models = [t for n, t in sorted(scored, reverse=True) if n >= 2][:2]
    # Rule-based "what it does" is only trusted when the article uses the "<City>-based <startup>" pattern;
    # "how it makes money" is NOT extracted automatically (too unreliable) - that lives in curated profiles.
    return {"what": what if what and BASED.search(what) else None, "financials": fin, "amount": amount,
            "stage": stage.title() if stage else None, "investors": investors}


def classify(title, blurb):
    text = f"{title} {blurb}"
    kind = next((l for l, rx in TYPES if rx.search(title)), None) or next((l for l, rx in TYPES if rx.search(text)), "Analysis")
    sector = next((l for l, rx in SECTORS if rx.search(text)), "Other")
    return kind, sector


def when(it):
    raw = it.findtext("pubDate") or ""
    try:
        return parsedate_to_datetime(raw).astimezone(IST).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return datetime.now(IST).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- main

def main():
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"items": []}
    known = {i["id"] for i in old["items"]}
    cutoff = (datetime.now(IST) - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
    fetched = 0
    fresh = []

    for name, region, url in FEEDS:
        try:
            root = ET.fromstring(get(url).lstrip("﻿"))
        except Exception as e:  # noqa: BLE001
            print(f"{name} feed failed: {e}", file=sys.stderr)
            continue
        for it in root.iter("item"):
            title = one_line(txt(it.findtext("title")))
            link = (it.findtext("link") or "").strip()
            if not title or not link:
                continue
            uid = "st-" + re.sub(r"\W+", "", link.split("//", 1)[-1])[-70:]
            date = when(it)
            if uid in known or date < cutoff:
                continue
            blurb = one_line(txt(it.findtext("description")))
            blurb = re.sub(r"\s*The post .*? appeared first on .*$", "", blurb)
            if NOISE.search(title):
                continue
            # startup-first outlets: keep everything except noise; general outlets: must clearly be about startups/deals
            hay = f"{title} {blurb}"
            if not STRICT.search(hay) and not (name in DEDICATED and FINANCE.search(hay)):
                continue
            body = article_body(it, link)
            if body is None and fetched < MAX_FETCH:
                body = fetch_page_body(link)
                fetched += 1
            kind, sector = classify(title, blurb)
            probe = f"{title} {blurb} {(body or '')[:1200]}"
            if name in INDIA_ONLY:
                region_of = "India"
            else:  # mixed outlets: India only if the story itself is visibly about India
                region_of = "India" if INDIA_MARK.search(probe) else "Global"
            facts = extract(title, blurb, body or "")
            if kind not in ("Funding", "IPO & Listing", "Acquisition"):
                facts["amount"] = facts["stage"] = None      # a figure in a results/analysis headline is not a deal size
            if kind != "Funding":
                facts["investors"] = None
            fresh.append({
                "id": uid, "source": name, "region": region_of, "title": title, "date": date, "url": link,
                "company": company_name(title), "type": kind, "sector": sector,
                "blurb": clip(blurb, 300), **facts, "first_seen": now,
            })

    # one story often appears in several outlets: keep the first, note the others
    merged, seen = [], {}
    for i in sorted(fresh, key=lambda x: x["date"], reverse=True):
        key = (i["company"] or "").lower() + "|" + i["type"] + "|" + i["date"] if i["company"] and i["type"] in ("Funding", "Acquisition", "IPO & Listing") else i["id"]
        if key in seen:
            seen[key].setdefault("also", []).append({"source": i["source"], "url": i["url"]})
            continue
        seen[key] = i
        merged.append(i)

    print(f"{len(merged)} new startup stories")
    if not merged:
        return
    items = sorted(merged + old["items"], key=lambda i: (i["date"], i["first_seen"]), reverse=True)[:MAX_ITEMS]
    OUT.write_text(json.dumps({"updated": now, "count": len(items), "items": items}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
