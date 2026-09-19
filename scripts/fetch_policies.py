"""Collect new Government of India policy items into data/items.json.

Fully self-contained: Python standard library only, no API keys, no AI service.
Run by GitHub Actions (.github/workflows/update.yml) twice a day, or by hand:
    python scripts/fetch_policies.py              # normal run
    python scripts/fetch_policies.py --backfill 14  # also pull the last 14 days of PIB releases

Sources (all official):
  PIB   - Press Information Bureau releases: Cabinet decisions, ministry schemes, subsidies, duties, budget items
  RBI   - notifications (directions, circulars) and policy press releases
  SEBI  - circulars, regulations, consultation papers, press releases (enforcement orders are dropped)

Summary = the government's own opening lines, trimmed. Nothing is paraphrased or invented.
Every item carries the link to the original document.
"""
import argparse, html, http.cookiejar, json, re, sys, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "items.json"
UA = {"User-Agent": "Mozilla/5.0 (updates-for-pal)"}
IST = timezone(timedelta(hours=5, minutes=30))
MAX_ITEMS = 3000
SUMMARY_CHARS = 460

# ---------------------------------------------------------------- filtering rules

# PIB ministries whose releases can carry policy that matters to an investor.
POLICY_MINISTRIES = re.compile(
    r"finance|commerce|corporate affairs|power|petroleum|coal|mines|steel|heavy industr|agricultur|"
    r"food|consumer affairs|chemicals|fertili[sz]er|pharmaceutical|electronics|information technology|"
    r"communications|telecom|civil aviation|ports|shipping|road transport|railways|housing|urban|"
    r"new and renewable|renewable|textiles|labour|rural development|health|environment|"
    r"tourism|micro|small and medium|msme|fisheries|animal husbandry|cooperation|cabinet|niti|"
    r"skill|jal shakti|water|earth sciences|space|atomic|external affairs|"
    r"planning|statistics|economic affairs|pib backgrounder|department of", re.I)

# A release is kept only if its title announces an ACTION: a decision, rule, rate, limit, scheme, agreement.
ACTION = re.compile(
    r"cabinet|approves?\b|approved|notif|amend|guidelines?|\brules\b|framework|regulations?\b|directions?\b|"
    r"circular|policy|policies|relax|eases?\b|imposes?|extends?\b|reduces?|hikes?|raises?|revis|ceiling|"
    r"limit|stockholding|come[s]? into force|\bact,? 20|\bbill\b|ordinance|launch(es|ed)?\b.*(scheme|portal|mission|round|guidelines|programme)|"
    r"auctions?\b|subsid|incentive|\bpli\b|\bmsp\b|minimum support|duty|duties|tariff|\bgst\b|"
    r"trade agreement|\bfta\b|negotiations?|protocol|allocat|outlay|sanction|\bfdi\b|disinvest|monetis|"
    r"advisory|standards of quality|semicon 2|deregulat|reform|\bban\b|prohibit|price cap|quota|licen[cs]e|"
    r"\b[23]\.0\b|budget|fiscal|borrowing|wage|pension|\bnps\b|\bups\b|interest rate|repo|crr|slr|"
    r"lending|priority sector|\bkyc\b|insurance|mutual fund|listing|\bipo\b|investor", re.I)

# Titles that are almost never policy (speeches, ceremonies, campaigns, enforcement, statistics, workshops).
NOISE_TITLE = re.compile(
    r"^text of|^english rendering|address by|inaugurat|condol|greets|greeting|wishes|anniversary|"
    r"appoints? (judges?|judicial)|appointment letters|keel laying|flags? off|visit(s)? to|\bvisits\b|"
    r"yoga|swachh|special campaign|fit india|photo|exhibition|felicitat|awards?\b|prize|"
    r"tweet|obituary|passes away|mann ki baat|^quiz|celebrat|workshop|conclave|conference|webinar|"
    r"gears? up|interacts?|reviews?\b|meets?\b|calls (on|for)|highlights|\bday \d|journey|success story|"
    r"seizes?|busts?|smuggl|arrest|crackdown|fraudulent|non-compliance|notices? to|facts on|helpline|"
    r"scholar|empower|strengthens? (welfare|educational|higher)|completes (three|two|one|\d+) years|"
    r"provisional estimates|index of industrial|consumer price|wholesale price|cumulative exports|exports? rise|"
    r"survey on|overseas direct investment for|weekly statistical|government stock|treasury bills|"
    r"state government securities|money market operations|reference rate|unsc|isil|al-qa|"
    r"vendor development|training (programme|centre)|foundation stone|lays foundation|assumes charge|chairs|signs mo[uU]|"
    r"training|forum|commemorative|postage|stamp|implant|commercialisation|drylands|organi[sz]es|technology transformation|surveillance|showcases|invites|welcomes passage|rajbhasha|hindi|sports|khelo|\bmos for\b", re.I)

SEBI_KEEP_PATH = re.compile(r"/(circulars|master-circulars|regulations|consultation-papers|guidelines|rules|acts|legal)[^/]*/")
SEBI_NOISE = re.compile(r"\border\b|adjudication|settlement|appeal no|remittance order|recovery|attachment|"
                        r"show cause|demand notice|debarr|interim|confirmatory|warrant|notice of|felicitat|techsprint|winners", re.I)
RBI_NOISE = re.compile(r"auction of|weekly statistical|treasury bills|state government securities|"
                       r"money market operations|reference rate|foreign exchange reserves|government stock|"
                       r"result of|liquidity adjustment|penalty|cancels?.*licen|survey on|overseas direct investment for|"
                       r"certificate of registration|^imposes|section 51a|unsc|isil|al-qa|variable rate reverse repo|vrrr", re.I)

SECTORS = [  # (label, regex on title + ministry) - first match wins
    ("Markets & Regulation", r"sebi|securities|mutual fund|\bipo\b|stock exchange|depositor|\bnps\b|pension fund|\bpfrda|\birdai|insurance"),
    ("Banking & Rates", r"\brbi\b|reserve bank|bank|repo|monetary|credit|loan|nbfc|lending|payment|upi|kyc|deposit|interest rate"),
    ("Tax, Duties & Trade", r"gst|customs|duty|duties|tariff|income tax|cbic|cbdt|tax|export|import|trade|anti-dumping|\bfta\b|commerce|dgft"),
    ("Budget & Fiscal", r"budget|fiscal|deficit|borrowing|expenditure|disinvest|monetis|outlay|finance"),
    ("Energy & Power", r"power|electric|petroleum|oil|gas|lng|coal|renewable|solar|wind|hydrogen|nuclear|atomic|fuel|ethanol"),
    ("Agriculture & Food", r"agricultur|farmer|\bmsp\b|fertili|crop|food|fisher|dairy|animal husbandry|kisan|cooperat|sugar|rice|wheat|pulses"),
    ("Infrastructure & Transport", r"railway|road|highway|port|shipping|aviation|airport|metro|housing|urban|smart cit|water|jal|infrastructure|logistic|corridor"),
    ("Industry & Manufacturing", r"steel|mines|mining|mineral|chemical|textile|manufactur|\bpli\b|industry|semiconductor|electronics|heavy industr|auto|defence production|msme|micro"),
    ("Technology & Telecom", r"telecom|spectrum|digital|\bit\b|information technology|ai\b|cyber|data protection|satellite|space|startup"),
    ("Health & Pharma", r"health|pharma|drug|medical|hospital|nlem|vaccine|ayush"),
    ("Labour & Social", r"labour|employment|epfo|\bepf|wage|skill|pension|welfare|rural|scheme|yojana|social|education|women|scholarship"),
    ("Environment & Climate", r"environment|climate|forest|emission|carbon|pollution|green"),
]
SECTORS = [(l, re.compile(p, re.I)) for l, p in SECTORS]

MAJOR = re.compile(
    r"cabinet approv|cabinet decision|union budget|approves? .*(crore|scheme|policy)|"
    r"notifies|repo rate|monetary policy|gst council|\bpli\b|\bmsp\b|minimum support price|"
    r"export duty|import duty|customs duty|anti-dumping|free trade agreement|\bfta\b|"
    r"master direction|new scheme|launch(es|ed)? .*scheme|disinvest|foreign direct investment|"
    r"labour codes?|regulations?, 20", re.I)


def sector_of(text):
    for label, rx in SECTORS:
        if rx.search(text):
            return label
    return "Other Policy"


# ---------------------------------------------------------------- helpers

def make_opener():
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def http_get(url, opener=None, data=None, retries=3):
    last = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA, data=data)
            with (opener.open(req, timeout=60) if opener else urllib.request.urlopen(req, timeout=60)) as r:
                return r.read().decode("utf-8-sig", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
    raise last


def clean(text):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def trim(text, limit=SUMMARY_CHARS):
    text = clean(text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("; "))
    return (cut[: end + 1] if end > limit * 0.5 else cut.rsplit(" ", 1)[0] + " ...").strip()


def iso(dt):
    return dt.astimezone(IST).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- PIB

def pib_session():
    op = make_opener()
    page = http_get("https://www.pib.gov.in/allRel.aspx?reg=3&lang=1", op)
    return op, page


def parse_pib_listing(page):
    out = []
    for m in re.finditer(r"<li><h3 class='font104'>(.*?)</h3><ul class='num'>(.*?)</ul>", page, re.S):
        ministry = clean(m.group(1))
        for title, href in re.findall(r"title='(.*?)' href='(.*?)'", m.group(2), re.S):
            prid = re.search(r"PRID=(\d+)", href)
            if prid:
                out.append((ministry, clean(title), prid.group(1)))
    return out


def pib_page_for_date(op, page, day):
    """Post the day / month / year drop-downs of PIB's release page to read an earlier day."""
    def field(name):
        m = re.search(r'name="%s"[^>]*value="([^"]*)"' % re.escape(name), page)
        return m.group(1) if m else ""
    form = {n: field(n) for n in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION")}
    form.update({
        "__EVENTTARGET": "ctl00$ContentPlaceHolder1$ddlday", "__EVENTARGUMENT": "",
        "ctl00$Bar1$ddlregion": "3", "ctl00$Bar1$ddlLang": "1",
        "ctl00$ContentPlaceHolder1$ddlMinistry": "0",
        "ctl00$ContentPlaceHolder1$ddlday": str(day.day),
        "ctl00$ContentPlaceHolder1$ddlMonth": str(day.month),
        "ctl00$ContentPlaceHolder1$ddlYear": str(day.year),
    })
    return http_get("https://www.pib.gov.in/allRel.aspx?reg=3&lang=1", op, urllib.parse.urlencode(form).encode())


def pib_detail(prid):
    url = f"https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID={prid}&reg=3&lang=1"
    try:
        page = http_get(url)
    except Exception as e:  # noqa: BLE001
        print(f"  PIB detail {prid} failed: {e}", file=sys.stderr)
        return "", None
    posted = re.search(r'id="PrDateTime"[^>]*>(.*?)</', page, re.S)
    date = None
    if posted:
        d = re.search(r"(\d{1,2} [A-Z]{3} \d{4})", posted.group(1))
        if d:
            date = datetime.strptime(d.group(1).title(), "%d %b %Y").strftime("%Y-%m-%d")
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    m = re.search(r"Posted On:.*?by PIB[^\n<]*", body, re.S)
    body = body[m.end():] if m else body
    body = re.split(r'id="RelLink"|Follow us on|Visitor Counter|Read this release in', body)[0]
    paras = [clean(p) for p in re.split(r"</p>|<br\s*/?>|</div>|</li>|\n\s*\n", body)]
    paras = [p for p in paras if len(p) > 70 and not re.match(r"^(ends?|\*+|pib|\(?release id)", p, re.I)]
    return trim(" ".join(paras[:3])), date


def wanted_pib(ministry, title):
    if NOISE_TITLE.search(title):
        return False
    if "Backgrounder" in ministry:
        return False
    if not POLICY_MINISTRIES.search(ministry):
        return False
    return bool(ACTION.search(title))


def collect_pib(known, backfill_days):
    items = []
    try:
        op, page = pib_session()
    except Exception as e:  # noqa: BLE001
        print(f"PIB unreachable: {e}", file=sys.stderr)
        return items
    days = [(datetime.now(IST).date(), page)]
    for back in range(1, backfill_days + 1):
        day = datetime.now(IST).date() - timedelta(days=back)
        try:
            days.append((day, pib_page_for_date(op, page, day)))
        except Exception as e:  # noqa: BLE001
            print(f"PIB backfill {day} failed: {e}", file=sys.stderr)
    for day, pg in days:
        for ministry, title, prid in parse_pib_listing(pg):
            uid = f"pib-{prid}"
            if uid in known or not wanted_pib(ministry, title):
                continue
            summary, posted = pib_detail(prid)
            date = posted or day.strftime("%Y-%m-%d")
            items.append({
                "id": uid, "source": "PIB", "ministry": ministry, "title": title,
                "summary": summary or "Open the release for full details.",
                "url": f"https://www.pib.gov.in/PressReleasePage.aspx?PRID={prid}",
                "date": date,
            })
    return items


# ---------------------------------------------------------------- RBI / SEBI

def rss_items(url):
    try:
        root = ET.fromstring(http_get(url).lstrip("﻿"))
    except Exception as e:  # noqa: BLE001
        print(f"Feed failed {url}: {e}", file=sys.stderr)
        return []
    return list(root.iter("item"))


def parse_date(s):
    s = (s or "").strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S", "%d %b, %Y %z", "%d %b %Y %H:%M:%S %z", "%d %b, %Y"):
        try:
            return datetime.strptime(re.sub(r"\s\+\d{4}$", "", s) if "%z" not in fmt else s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return datetime.now(IST).strftime("%Y-%m-%d")


def collect_rbi(known):
    items = []
    for feed, kind in (("https://www.rbi.org.in/notifications_rss.xml", "Notification"),
                       ("https://www.rbi.org.in/pressreleases_rss.xml", "Press release")):
        for it in rss_items(feed):
            title = clean(it.findtext("title"))
            link = (it.findtext("link") or "").strip()
            uid = "rbi-" + re.sub(r"\W+", "", link.split("?")[-1] or title)[:40]
            if uid in known or RBI_NOISE.search(title) or not title:
                continue
            if kind == "Press release" and not ACTION.search(title):
                continue
            desc = clean(it.findtext("description"))
            desc = re.sub(r"^RBI/\d{4}-\d{2}/\d+\s+\S+\s+[A-Za-z]+ \d{1,2}, \d{4}\s+", "", desc)
            items.append({
                "id": uid, "source": "RBI", "ministry": f"Reserve Bank of India · {kind}", "title": title,
                "summary": trim(desc) or "Open the document for full details.",
                "url": link, "date": parse_date(it.findtext("pubDate")),
            })
    return items


def collect_sebi(known):
    items = []
    for it in rss_items("https://www.sebi.gov.in/sebirss.xml"):
        title = clean(it.findtext("title"))
        link = (it.findtext("link") or "").strip()
        if not title or SEBI_NOISE.search(title) or "/enforcement/" in link:
            continue
        if not SEBI_KEEP_PATH.search(link) and not ACTION.search(title):
            continue
        uid = "sebi-" + re.sub(r"\W+", "", link.rsplit("/", 1)[-1])[:60]
        if uid in known:
            continue
        desc = clean(it.findtext("description"))
        section = re.search(r"/(circulars|regulations|press-releases|consultation-papers|master-circulars|guidelines|"
                            r"rules|acts|reports|legal)[^/]*/", link)
        items.append({
            "id": uid, "source": "SEBI", "ministry": "SEBI" + (f" · {section.group(1).replace('-', ' ')}" if section else ""),
            "title": title,
            "summary": trim(desc) if desc and desc != title else "Open the document for full details.",
            "url": link, "date": parse_date(it.findtext("pubDate")),
        })
    return items


# ---------------------------------------------------------------- main

def enrich(item):
    text = f"{item['title']} {item['ministry']}"
    if item["source"] == "SEBI":
        item["sector"] = "Markets & Regulation"
    elif item["source"] == "RBI":
        item["sector"] = "Banking & Rates"
    else:
        item["sector"] = sector_of(text)
    item["major"] = bool(MAJOR.search(item["title"]))
    return item


RBI_TWIN = re.compile(r"^(Reserve Bank of India) [(](.+?) [–-] (.+?)[)] (.*)$")


def norm_title(t):
    return re.sub(r"[^a-z0-9]+", "", t.lower())


def dedupe_and_group(items):
    """Drop repeated titles (same release under two ministries); fold RBI's per-bank-category twins into one card."""
    seen, out, groups = set(), [], {}
    for it in items:
        key = norm_title(it["title"])
        if key in seen:
            continue
        seen.add(key)
        m = RBI_TWIN.match(it["title"]) if it["source"] == "RBI" else None
        if not m:
            out.append(it)
            continue
        gk = (m.group(3), m.group(4), it["date"])
        if gk in groups:
            g = groups[gk]
            g["_who"].append(m.group(2))
            g.setdefault("links", []).append({"label": m.group(2), "url": it["url"]})
        else:
            it["_who"] = [m.group(2)]
            it["_stem"] = (m.group(1), m.group(3), m.group(4))
            it["links"] = [{"label": m.group(2), "url": it["url"]}]
            groups[gk] = it
            out.append(it)
    for it in out:
        who = it.pop("_who", None)
        stem = it.pop("_stem", None)
        if who and len(who) > 1:
            it["title"] = f"{stem[0]} ({stem[1]}) {stem[2]}: issued for {len(who)} bank categories"
            it["summary"] = "Separate directions issued for: " + ", ".join(who) + ". " + it["summary"]
        elif who:
            it.pop("links", None)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", type=int, default=0, help="also read this many previous days of PIB releases")
    args = ap.parse_args()

    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"items": []}
    known = {i["id"] for i in old["items"]}
    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")

    fresh = collect_pib(known, args.backfill) + collect_rbi(known) + collect_sebi(known)
    fresh = [enrich(i) for i in dedupe_and_group(fresh)]
    for i in fresh:
        i["first_seen"] = now
    print(f"{len(fresh)} new policy items")
    if not fresh:
        return

    items = sorted(fresh + old["items"], key=lambda i: (i["date"], i["first_seen"]), reverse=True)[:MAX_ITEMS]
    OUT.write_text(json.dumps({"updated": now, "count": len(items), "items": items},
                              ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
