"""Build the Front Page: the 15-20 highest-priority stories across the three desks -> data/front.json.

Python standard library only. Run after the collectors:
    python scripts/build_front_page.py

How "priority" is decided (rule-based, transparent, no AI):
  every story gets points from named rules (a Cabinet decision, a regulator direction, a large deal, an official
  immigration notice, a change to a salary threshold or settlement clock, coverage by many outlets ...) plus a
  recency bonus. The rules that fired are written on the card as "Why it is here", so the ranking can be audited.
  Scores are converted to a 0-100 scale per desk so no desk crowds out the others, then the best stories are picked
  with a quota per desk (POLICY / STARTUPS / IMMIGRATION) and a cap on repeats of one country or company.
Edit the rule tables below to change what counts as important.
"""
import json, re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
IST = timezone(timedelta(hours=5, minutes=30))
INR_PER_USD = 95.0          # approximate; only used to compare deal sizes
QUOTA = {"Policy": 7, "Startups": 6, "Immigration": 5}     # 18 stories
MIN_TOTAL, MAX_TOTAL = 15, 20
WINDOW_DAYS = 7


def load(name):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"items": []}


def age_days(date, today):
    return (today - datetime.strptime(date, "%Y-%m-%d").date()).days


def recency(days):
    return {0: 3, 1: 2, 2: 1}.get(days, 0)


def R(p):
    return re.compile(p, re.I)


# ---------------------------------------------------------------- policy rules: (regex on title, points, reason)
POLICY_RULES = [
    (R(r"cabinet"), 6, "Cabinet decision"),
    (R(r"union budget|budget (?:estimate|speech|allocation)"), 6, "Budget item"),
    (R(r"\bgst\b|gst council"), 5, "GST change"),
    (R(r"customs duty|export duty|import duty|anti-dumping|tariff|safeguard duty"), 5, "Duty or tariff change"),
    (R(r"repo|monetary policy|\bcrr\b|\bslr\b|interest rate"), 5, "Rates and liquidity"),
    (R(r"master direction|amendment directions|regulations?, 20|circular|consultation paper"), 4, "Regulator rulebook change"),
    (R(r"\bmsp\b|minimum support price|subsid|\bpli\b|incentive"), 4, "Subsidy or incentive"),
    (R(r"wage ceiling|epfo|labour code|minimum wage"), 4, "Labour and pension rule"),
    (R(r"disinvest|privati[sz]|monetis|\bfdi\b|foreign direct"), 4, "Capital and ownership policy"),
    (R(r"free trade|trade agreement|\bfta\b|preferential trade|mercosur|comprehensive economic"), 4, "Trade agreement"),
    (R(r"come[s]? into force|\bact,? 20|\bbill\b|ordinance"), 3, "New law or act"),
    (R(r"relax|eases|extends|amend|notif|guidelines|rules"), 2, "Rule change"),
    (R(r"kyc|priority sector|lending|credit|insurance|mutual fund|\bnps\b|\bipo\b"), 2, "Touches financial markets"),
    (R(r"semicon|semiconductor|critical minerals|green hydrogen|\bev\b|electric vehicle"), 2, "Strategic sector"),
    (R(r"road over bridge|level crossing|doubling|new rail line|electric traction|land pooling"), -3, "Routine project approval"),
    (R(r"\bmou\b|advisory|workshop|awareness"), -2, "Routine"),
]
POLICY_SOURCE = {"RBI": (2, "Regulator: RBI"), "SEBI": (2, "Regulator: SEBI")}
POLICY_MINISTRY = [(R(r"cabinet"), 2, "Cabinet"), (R(r"finance|economic affairs|revenue"), 2, "Ministry of Finance"),
                   (R(r"commerce"), 1, "Commerce")]
AMOUNT_CR = re.compile(r"(?:₹|Rs\.?)\s?([\d,]+(?:\.\d+)?)\s?(lakh crore|crore|cr\b)", re.I)


def crore_value(text):
    m = AMOUNT_CR.search(text or "")
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    return v * 100000 if "lakh" in m.group(2).lower() else v


def score_policy(it, today):
    pts, why = 0, []
    t = it["title"]
    for rx, p, reason in POLICY_RULES:
        if rx.search(t):
            pts += p
            if p > 0:
                why.append(reason)
    if it.get("major"):
        pts += 2
    src = POLICY_SOURCE.get(it["source"])
    if src:
        pts += src[0]
        why.append(src[1])
    for rx, p, reason in POLICY_MINISTRY:
        if rx.search(it.get("ministry", "")):
            pts += p
            why.append(reason)
            break
    cr = crore_value(t + " " + it.get("summary", ""))
    if cr and cr >= 10000:
        pts += 3
        why.append("Large outlay (Rs 10,000 Cr or more)")
    elif cr and cr >= 1000:
        pts += 1
    pts += recency(age_days(it["date"], today))
    return pts, why


# ---------------------------------------------------------------- startup rules
TYPE_PTS = {"IPO & Listing": 4, "Acquisition": 4, "Funding": 3, "Shutdown & Layoffs": 3, "Financials": 2, "Launch & Product": 1}
USD = re.compile(r"(?:US\$|USD|\$)\s?([\d,]+(?:\.\d+)?)\s?(billion|bn|b\b|million|mn|m\b|k\b)?", re.I)
INR = re.compile(r"(?:₹|Rs\.?)\s?([\d,]+(?:\.\d+)?)\s?(lakh crore|crore|cr\b)", re.I)


def usd_million(text):
    """Largest money figure in the text, in USD million (approximate)."""
    best = 0.0
    for m in USD.finditer(text or ""):
        v = float(m.group(1).replace(",", ""))
        u = (m.group(2) or "").lower()
        v = v * 1000 if u in ("billion", "bn", "b") else v if u in ("million", "mn", "m") else v / 1000 if u == "k" else v / 1e6
        best = max(best, v)
    for m in INR.finditer(text or ""):
        v = float(m.group(1).replace(",", ""))
        cr = v * 100000 if "lakh" in m.group(2).lower() else v
        best = max(best, cr * 1e7 / INR_PER_USD / 1e6)
    return best


def score_startup(it, today, profile_urls):
    pts, why = TYPE_PTS.get(it["type"], 0), []
    if it["type"] in TYPE_PTS and it["type"] != "Launch & Product":
        why.append(it["type"])
    text = f"{it['title']} {it.get('amount') or ''}"
    mn = usd_million(text)
    if mn >= 500:
        pts += 5; why.append(f"Very large figure in headline (about ${mn:,.0f}M: round or valuation)")
    elif mn >= 100:
        pts += 4; why.append(f"Large deal (about ${mn:,.0f}M)")
    elif mn >= 25:
        pts += 3; why.append(f"Sizeable deal (about ${mn:,.0f}M)")
    elif mn >= 5:
        pts += 1
    if it["url"] in profile_urls:
        pts += 4; why.append("Startup File written (what they do, how they make money)")
    if it.get("region") == "India":
        pts += 1
    if re.search(r"unicorn|valuation|sebi (?:nod|approval|greenlight)|drhp|pre-ipo|profit|turns profitable", it["title"], re.I):
        pts += 2; why.append("Valuation, listing or profitability signal")
    n = len(it.get("also") or [])
    if n:
        pts += min(n, 3); why.append(f"Also covered by {n} other outlet(s)")
    if it["type"] == "Analysis":
        pts -= 1
    pts += recency(age_days(it["date"], today))
    return pts, why


# ---------------------------------------------------------------- immigration rules
IMM_TOPIC = {"PR / Settlement": 4, "Citizenship": 4, "Salary threshold": 3, "Quota / Caps": 3, "Work visa": 3,
             "Politics / Election": 1, "Student / Graduate": 1, "General": 0}
IMM_TOPIC_WHY = {"PR / Settlement": "Affects permanent residence", "Citizenship": "Affects citizenship",
                 "Salary threshold": "Salary threshold change", "Quota / Caps": "Quota or cap change",
                 "Work visa": "Affects work visas", "Politics / Election": "Political signal on immigration"}
IMM_ACTION = R(r"new rules?|announces?|scrap|abolish|cut|cap\b|raise|tighten|crackdown|threshold|extend|reform|ban|"
               r"introduce|overhaul|changes?|passes?|approves?|delay|earned settlement|10 years|points")
TOP_OUTLETS = R(r"reuters|bloomberg|bbc|guardian|dw\b|dw\.com|al jazeera|associated press|\bap\b|financial times|ft\.com|"
                r"new york times|economist|times of india|hindustan times|indian express|the hindu|straits times|nikkei|"
                r"abc news|sbs|rnz|cbc|globe and mail|the local|euronews|politico")


def score_immigration(it, today, counts):
    pts, why = IMM_TOPIC.get(it["topic"], 0), []
    if it["topic"] in IMM_TOPIC_WHY:
        why.append(IMM_TOPIC_WHY[it["topic"]])
    if it.get("official"):
        pts += 3; why.append("Official government notice")
    if IMM_ACTION.search(it["title"]):
        pts += 2; why.append("Announces a change")
    n = counts.get((it["country"], it["date"]), 0)
    if n >= 8:
        pts += 3; why.append(f"Major story ({n} headlines that day)")
    elif n >= 4:
        pts += 1
    if TOP_OUTLETS.search(it["source"]):
        pts += 1
    if re.search(r"india|indian", it["title"], re.I):
        pts += 2; why.append("Mentions India or Indians")
    pts += recency(age_days(it["date"], today))
    return pts, why


# ---------------------------------------------------------------- selection
STOP = set("the a an of to in on for and or as at by with from is are be its it this that new how what why will after over "
           "amid says say rs cr crore lakh india indian government govt ministry minister".split())


def tokens(title):
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {w.rstrip("s") for w in words if w not in STOP and len(w) > 2}


def dedupe(pool):
    """Drop stories that are the same event under another headline (word overlap), keeping the higher score."""
    pool = sorted(pool, key=lambda x: x[0], reverse=True)
    kept, kept_tokens = [], []
    for sc, why, it in pool:
        t = tokens(it["title"])
        dup = any(t and k and len(t & k) / len(t | k) >= 0.4 for k in kept_tokens)
        if not dup:
            kept.append((sc, why, it))
            kept_tokens.append(t)
    return kept


def top_of(desk, scored, quota, key_of):
    """scored: list of (score, why, item). Returns the best `quota` with at most 1 story per key (country / company)."""
    scored.sort(key=lambda x: (x[0], x[2]["date"]), reverse=True)
    out, used = [], {}
    limit = 1 if desk in ("Immigration", "Startups") else 99
    for sc, why, it in scored:
        k = key_of(it)
        if k and used.get(k, 0) >= limit:
            continue
        used[k] = used.get(k, 0) + 1
        out.append((sc, why, it))
        if len(out) >= quota:
            break
    return out


def main():
    today = datetime.now(IST).date()
    horizon = (today - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")

    policy = [i for i in load("items.json")["items"] if i["date"] >= horizon]
    startups = [i for i in load("startups.json")["items"] if i["date"] >= horizon]
    imm = [i for i in load("immigration.json")["items"] if i["date"] >= horizon]
    off_topic = re.compile(r"sahrawi|western sahara|ratcliffe|man united", re.I)
    policy, startups, imm = ([i for i in x if not off_topic.search(i["title"])] for x in (policy, startups, imm))
    profile_urls = {p["key"] for p in load("profiles.json").get("profiles", [])}
    counts = {}
    for i in imm:
        counts[(i["country"], i["date"])] = counts.get((i["country"], i["date"]), 0) + 1

    pools = {
        "Policy": [(*score_policy(i, today), i) for i in policy],
        "Startups": [(*score_startup(i, today, profile_urls), i) for i in startups],
        "Immigration": [(*score_immigration(i, today, counts), i) for i in imm],
    }
    keyfn = {
        "Policy": lambda i: None,
        "Startups": lambda i: (i.get("company") or i["title"][:18]).lower(),
        "Immigration": lambda i: i["country"],
    }
    # per-desk 0-100 scale against that desk's best score in the window, so desks compare fairly
    picked = []
    for desk, pool in pools.items():
        top_score = max([p[0] for p in pool] + [1])
        for sc, why, it in top_of(desk, dedupe(pool), QUOTA[desk] + 3, keyfn[desk]):
            picked.append({"desk": desk, "score": sc, "scaled": round(100 * sc / top_score), "why": why, "item": it})

    # take each desk's quota first (best by score), then top up to MIN_TOTAL from the leftovers by scaled score
    chosen, left = [], []
    for desk in QUOTA:
        mine = sorted([p for p in picked if p["desk"] == desk], key=lambda p: p["score"], reverse=True)
        chosen += mine[: QUOTA[desk]]
        left += mine[QUOTA[desk]:]
    left.sort(key=lambda p: p["scaled"], reverse=True)
    while len(chosen) < MIN_TOTAL and left:
        chosen.append(left.pop(0))
    chosen = [c for c in chosen if c["score"] > 0][:MAX_TOTAL]
    chosen.sort(key=lambda p: (p["scaled"], p["item"]["date"]), reverse=True)

    out = []
    for rank, c in enumerate(chosen, 1):
        it = c["item"]
        entry = {
            "rank": rank, "desk": c["desk"], "must_read": rank <= 5, "score": c["score"], "priority": c["scaled"],
            "title": it["title"], "url": it["url"], "date": it["date"],
            "source": it.get("source") or it.get("ministry", ""),
            "label": it.get("sector") or it.get("countryLabel") or it.get("country", ""),
            "summary": it.get("summary") or it.get("blurb") or "",
            "why": c["why"][:4] or ["High on the desk's ranking"],
        }
        if c["desk"] == "Immigration":
            entry["label"] = it["country"].replace("-", " ").title().replace("Uk", "United Kingdom")
        if c["desk"] == "Startups":
            entry["label"] = f"{it['region']} · {it['sector']}"
        out.append(entry)

    now = datetime.now(IST)
    (DATA / "front.json").write_text(json.dumps({
        "edition": now.strftime("%Y-%m-%d"), "built": now.strftime("%Y-%m-%d %H:%M IST"),
        "count": len(out), "by_desk": {d: sum(1 for o in out if o["desk"] == d) for d in QUOTA},
        "items": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"front page: {len(out)} stories", {d: sum(1 for o in out if o['desk'] == d) for d in QUOTA})


if __name__ == "__main__":
    main()
