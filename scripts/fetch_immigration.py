"""Collect immigration and citizenship rule-change news into data/immigration.json.

Python standard library only, no API keys, no AI service.
    python scripts/fetch_immigration.py

Two kinds of source:
  official  - GOV.UK (UK Visas and Immigration) atom feed, IRCC (Canada) news feed. Marked official in the data.
  press     - Google News RSS search, one query per shortlisted country, last 30 days. Headline + outlet + link only.
              Visa-agency marketing sites are filtered out by outlet name. Read the original before acting.

Most immigration departments block automated feeds (403/404), so those countries are covered by press headlines only.
The Country Files (data/immigration_files.json) are hand-written and separate from this feed.
"""
import html, json, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "immigration.json"
UA = {"User-Agent": "Mozilla/5.0 (updates-for-pal)"}
IST = timezone(timedelta(hours=5, minutes=30))
MAX_ITEMS = 1500
KEEP_DAYS = 45

COUNTRIES = {  # id (matches immigration_files.json) -> search name
    "germany": "Germany", "uk": "UK", "canada": "Canada", "australia": "Australia", "new-zealand": "New Zealand",
    "netherlands": "Netherlands", "switzerland": "Switzerland", "sweden": "Sweden", "denmark": "Denmark",
    "belgium": "Belgium", "luxembourg": "Luxembourg", "iceland": "Iceland", "finland": "Finland", "austria": "Austria",
    "norway": "Norway", "spain": "Spain", "france": "France", "japan": "Japan", "korea": "South Korea",
}
MENTION = {
    "germany": r"german|berlin|bundestag|afd", "uk": r"\buk\b|britain|british|england|london|home office|starmer|\bilr\b|gov\.uk",
    "canada": r"canad|ottawa|ircc|express entry", "australia": r"austral|canberra|albanese",
    "new-zealand": r"new zealand|\bnz\b|kiwi|inz\b", "netherlands": r"netherlands|dutch|holland|hague",
    "switzerland": r"swiss|switzerland", "sweden": r"swed", "denmark": r"danish|denmark", "belgium": r"belgi",
    "luxembourg": r"luxembourg", "iceland": r"iceland", "finland": r"finland|finnish", "austria": r"austria",
    "norway": r"norw", "spain": r"spain|spanish", "france": r"france|french|paris", "japan": r"japan",
    "korea": r"korea",
}
LABEL = {"uk": "United Kingdom", "korea": "South Korea"}

TERMS = ('(visa OR immigration OR citizenship OR naturalisation OR "permanent residence" OR "work permit" '
         'OR "Blue Card" OR settlement OR "skilled worker" OR "residence permit")')

RELEVANT = re.compile(
    r"visa|immigra|citizenship|naturali[sz]ation|permanent residen|residence permit|work permit|blue card|"
    r"earned settlement|settlement (?:rules|route|scheme|period)|skilled (?:worker|migrat)|indefinite leave|\bILR\b|express entry|"
    r"talent passport|quota|salary threshold|points system|work(?:ing)? holiday|residency|foreign workers?|"
    r"foreign talent|migration (?:policy|rules|levels|cap|curb|plan)|net migration|levels plan", re.I)
NOISE = re.compile(r"sahrawi|western sahara|ratcliffe|man united|wheat|harvest|israel|palestin|west bank|gaza|hajj|ukrain|riot|clash|protest|rally|police|crime|arrest|killed|attack|"
                   r"stabbing|pattaya|roman|archaeolog|meta faces|us student|us colleges|h-?1b|trump|asylum seekers?|refugee|deport|smuggl|border patrol|illegal migrants?|small boats|channel crossing|"
                   r"ice raid|detention|stateless|trafficking", re.I)
BLOCK = re.compile(r"legit|ua\.news|yen news|jpost|pattaya|world socialist|sightmagazine|y-?axis|visa ?guide|visaverge|jobbatical|atozserwis|consilio|lottalingo|nordic life guide|"
                   r"golden visa|immigrationxperts|abroadmate|visasupdate|wheretoemigrate|hiliv|migaku|"
                   r"immigrantinvest|globalcitizensolutions|bestmigration|visaflow|kagan|aldaglegal|employsome|"
                   r"navigatorjapan|libertymundo|visashogun|japan-visa|iasservices|osbournepinner|lawsentis|"
                   r"immigrationworld|shiksha|admitkard|pioverseas|mylegalpal|findmyvisa|visamet|i-migrator", re.I)

TOPICS = [
    ("Salary threshold", r"salary|threshold|minimum wage|income requirement|pay limit|earnings"),
    ("Citizenship", r"citizenship|naturali[sz]ation|passport"),
    ("PR / Settlement", r"permanent residen|settlement|indefinite leave|\bILR\b|long-term resident|residence card|green card"),
    ("Student / Graduate", r"student|graduate|post-study|university"),
    ("Quota / Caps", r"quota|cap\b|caps\b|levels plan|ceiling|planning levels|limit"),
    ("Politics / Election", r"election|party|afd|referendum|vote|government plans|manifesto|coalition|parliament|bill\b"),
    ("Work visa", r"work visa|work permit|skilled|blue card|talent|employer|sponsor|job seeker|opportunity card"),
]
TOPICS = [(t, re.compile(p, re.I)) for t, p in TOPICS]


def get(url):
    last = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45) as r:
                return r.read().decode("utf-8-sig", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5)
    raise last


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def topic_of(text):
    return next((t for t, rx in TOPICS if rx.search(text)), "General")


def norm(t):
    return re.sub(r"[^a-z0-9]+", "", t.lower())[:90]


def google_news(cid, name, cutoff):
    q = urllib.parse.quote(f"{name} {TERMS} when:30d")
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    try:
        root = ET.fromstring(get(url))
    except Exception as e:  # noqa: BLE001
        print(f"  google news {name} failed: {e}", file=sys.stderr)
        return []
    out = []
    for it in root.iter("item"):
        raw = clean(it.findtext("title"))
        src_el = it.find("source")
        source = clean(src_el.text) if src_el is not None and src_el.text else ""
        title = re.sub(r"\s+-\s+" + re.escape(source) + r"$", "", raw) if source else raw
        if not source and " - " in raw:
            title, source = raw.rsplit(" - ", 1)
        if BLOCK.search(source) or not RELEVANT.search(title) or NOISE.search(title):
            continue
        if not re.search(MENTION[cid], title, re.I):
            continue
        try:
            date = parsedate_to_datetime(it.findtext("pubDate")).astimezone(IST).strftime("%Y-%m-%d")
        except Exception:  # noqa: BLE001
            continue
        if date < cutoff:
            continue
        out.append({"country": cid, "title": title, "source": source or "Google News", "official": False,
                    "date": date, "url": (it.findtext("link") or "").strip(), "topic": topic_of(title)})
    return out


def govuk(cutoff):
    try:
        root = ET.fromstring(get("https://www.gov.uk/government/organisations/uk-visas-and-immigration.atom"))
    except Exception as e:  # noqa: BLE001
        print(f"  gov.uk failed: {e}", file=sys.stderr)
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for e in root.findall("a:entry", ns):
        title = clean(e.findtext("a:title", namespaces=ns))
        link = e.find("a:link", ns)
        upd = (e.findtext("a:updated", namespaces=ns) or "")[:10]
        if not upd or upd < cutoff or not RELEVANT.search(title) or NOISE.search(title):
            continue
        out.append({"country": "uk", "title": title, "source": "GOV.UK (UK Visas and Immigration)", "official": True,
                    "date": upd, "url": link.get("href") if link is not None else "", "topic": topic_of(title)})
    return out


def ircc(cutoff):
    url = ("https://api.io.canada.ca/io-server/gc/news/en/v2?dept=departmentofcitizenshipandimmigration"
           "&sort=publishedDate&orderBy=desc&pick=40&format=atom&atomtitle=IRCC")
    try:
        root = ET.fromstring(get(url))
    except Exception as e:  # noqa: BLE001
        print(f"  IRCC failed: {e}", file=sys.stderr)
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for e in root.findall("a:entry", ns):
        title = clean(e.findtext("a:title", namespaces=ns))
        upd = (e.findtext("a:updated", namespaces=ns) or "")[:10]
        link = e.find("a:link", ns)
        if not upd or upd < cutoff or not RELEVANT.search(title) or NOISE.search(title):
            continue
        out.append({"country": "canada", "title": title, "source": "IRCC (Government of Canada)", "official": True,
                    "date": upd, "url": link.get("href") if link is not None else "", "topic": topic_of(title)})
    return out


def main():
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"items": []}
    # re-apply the current filters to what is already stored, so tightening a rule also cleans old items
    old["items"] = [i for i in old["items"]
                    if not NOISE.search(i["title"]) and not BLOCK.search(i["source"]) and RELEVANT.search(i["title"])
                    and re.search(MENTION.get(i["country"], "."), i["title"], re.I)]
    known = {i["id"] for i in old["items"]}
    cutoff = (datetime.now(IST) - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")

    found = govuk(cutoff) + ircc(cutoff)
    for cid, name in COUNTRIES.items():
        found += google_news(cid, name, cutoff)
        time.sleep(1.0)

    seen, fresh = set(), []
    for it in sorted(found, key=lambda x: (not x["official"], x["date"]), reverse=False):
        key = norm(it["title"])
        it["id"] = f"im-{it['country']}-{key[:60]}"
        if key in seen or it["id"] in known:
            continue
        seen.add(key)
        it["first_seen"] = now
        fresh.append(it)
    # one event is covered by dozens of outlets: keep at most 4 headlines per country/day/topic (official first)
    count, capped = {}, []
    for it in fresh:
        k = (it["country"], it["date"], it["topic"])
        count[k] = count.get(k, 0) + 1
        if count[k] <= 4:
            capped.append(it)
    fresh = capped
    print(f"{len(fresh)} new immigration items")
    items = sorted(fresh + old["items"], key=lambda i: (i["date"], i["first_seen"]), reverse=True)[:MAX_ITEMS]
    OUT.write_text(json.dumps({"updated": now, "count": len(items), "items": items}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
