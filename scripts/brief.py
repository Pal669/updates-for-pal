"""Write a self-contained brief for every story, so the reader rarely needs to open the link -> data/briefs.json.

    python scripts/brief.py                # brief the stories that have no brief yet (default budget 120 page fetches)
    python scripts/brief.py --budget 500   # bigger first run

Each brief has:
  what     the 2-3 sentences of the article that carry the news, lifted from the article's own text
  facts    numbers, dates, amounts and thresholds found in the article
  why      "why this affects you": rules that map the story onto Ashish's situation (advisor and investor in India,
           planning to move abroad, learning how startups make money) and onto his own Country Files
  watch    forward-looking lines (deadlines, next steps) plus the watch item from the Country File
  verdict  whether the original is worth opening (skip / worth / open)

Default mode is rule-based and needs nothing but Python: it EXTRACTS sentences, it does not understand or paraphrase them,
and the "why" lines come from a rules table you can edit (IMPACT_* below). For real reading comprehension you can plug in an
AI model of your choice: set BRIEF_LLM_KEY (and BRIEF_LLM_PROVIDER=anthropic|openai, BRIEF_LLM_MODEL, optionally
BRIEF_LLM_BASE_URL) as environment variables or GitHub secrets. With no key nothing external is called.
That AI path has NOT been tested (no key was available when it was written); the rule-based path is what runs today.
"""
import argparse, json, os, re, sys, time, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import enrich as E  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
OUT = DATA / "briefs.json"
IST = timezone(timedelta(hours=5, minutes=30))
IMM_DAYS = 21

PROFILE = ("Ashish Pal: AVP financial analyst and independent investment advisor in Delhi (about Rs 4 Cr of client AUM), "
           "building an advisory business and a finance audience, studying how startups make money, and planning to move "
           "abroad for work and permanent residence (shortlist of 19 countries).")


def load(name):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


# ---------------------------------------------------------------- reading the article
ABBR = re.compile(r"\b(Rs|Shri|Dr|Mr|Mrs|Ms|Smt|Sh|No|St|Lt|Gen|vs|approx|Co|Ltd|Pvt|Inc|Cr|Mn|Bn|U\.S|e\.g|i\.e)\.", re.I)


JUNK = re.compile(r"search submit|toggle|mega menu|topics latest|linkedin|facebook|instagram|youtube|mastodon|bluesky|©|"
                  r"\bmin read\b|\d+ stories|subscribe|newsletter|sign in|follow us|advertis|image credits?|"
                  r"photo:|read more|also read|share this|click here|listen to", re.I)


def split_sentences(text, title=""):
    t = ABBR.sub(lambda m: m.group(0)[:-1] + "․", text)
    at = t.lower().find(title.lower()) if title else -1
    if 0 <= at < 12:
        t = t[at + len(title):].lstrip(" .:-")                       # drop a repeated headline
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9“\"'₹$(])", t)
    out = [p.replace("․", ".").strip() for p in parts if len(p.strip()) >= 30]
    return [p for p in out if not JUNK.search(p)]


def article_text(url):
    """Best-effort full text of the story ('' if it cannot be read)."""
    real = url
    if "news.google.com" in url:
        real = E.resolve_google(url)
        if not real:
            return ""
    m = re.search(r"pib\.gov\.in/.*PRID=(\d+)", real)
    if m:
        real = f"https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID={m.group(1)}&reg=3&lang=1"
    try:
        page, _ = E.http(real, timeout=20)
    except Exception:  # noqa: BLE001
        return ""
    if "PressReleaseIframePage" in real:
        body = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
        mm = re.search(r"Posted On:.*?by PIB[^\n<]*", body, re.S)
        body = body[mm.end():] if mm else body
        body = re.split(r'id="RelLink"|Follow us on|Visitor Counter', body)[0]
        paras = [E.clean_text(p) for p in re.split(r"</p>|<br\s*/?>|</div>|</li>|\n\s*\n", body)]
    else:
        am = re.search(r"<article.*?</article>", page, re.S | re.I)
        chunk = am.group(0) if am else page
        paras = [E.clean_text(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", chunk, re.S | re.I)]
        if sum(len(p) for p in paras) < 300:                     # tables etc. (RBI notifications)
            paras = [E.clean_text(chunk)[:6000]]
    paras = [p for p in paras if len(p) >= 45 and not E.BOILER.search(p) and not re.match(r"^(ends?|\*+|pib|\(?release id)", p, re.I)]
    return " ".join(paras)[:9000]


# ---------------------------------------------------------------- extractive summary
STOP = set("the a an of to in on for and or as at by with from is are was were be its it this that new will has have had "
           "into over under after amid says said say not but also more than their they which who".split())
ACTION = re.compile(r"approv|announc|rais|impos|extend|relax|cut|introduc|launch|amend|notif|allow|ban|require|mandat|"
                    r"decid|sign|issu|clear|tighten|scrap|lift|revis|effective|come[s]? into force|will |must ", re.I)
TIME = re.compile(r"\b(?:from|by|before|until|effective|w\.e\.f\.?)\s+(?:\d{1,2}\s+)?(?:January|February|March|April|May|June|July|"
                  r"August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?(?:\s+\d{4})?|"
                  r"\b(?:next|this)\s+(?:week|month|quarter|year)\b|\bin\s+(?:Q[1-4]|the\s+(?:first|second|third|fourth)\s+quarter)\b|"
                  r"\b(?:expected|proposed|scheduled|due|deadline|awaits?|pending)\b", re.I)
NUM = re.compile(r"(?:₹|Rs\.?|US\$|\$|USD|EUR|GBP|£|€)\s?\d|\d[\d,\.]*\s?(?:%|per cent|crore|lakh|million|billion|Cr|Mn|Bn|years?|months?|days?)|\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\b", re.I)


WATCH = re.compile(r"\b(?:from|by|before|until|effective|w\.e\.f\.?)\s+(?:\d{1,2}\s+)?(?:January|February|March|April|May|June|July|August|"
                   r"September|October|November|December)\b|\bnext (?:week|month|quarter|year)\b|\bdeadline\b|\bscheduled\b|\bproposed\b|"
                   r"\bawaits?\b|\bpending\b|\bcomes? into force\b|\bin (?:Q[1-4]|the coming (?:weeks|months))\b|\bby (?:20\d\d|end of)", re.I)


def toks(s):
    return {w.rstrip("s") for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in STOP and len(w) > 2}


def pick_what(title, sents):
    tt = toks(title)
    scored = []
    for i, s in enumerate(sents[:24]):
        sc = max(0.0, 3.0 - i * 0.35)
        sc += 1.4 if NUM.search(s) else 0
        sc += 1.0 if ACTION.search(s) else 0
        st = toks(s)
        sc += 3.0 * len(tt & st) / max(len(tt | st), 1)
        if len(s) > 340:
            sc -= 1.2
        if re.search(r"\b(said|says|told|added|noted)\b", s):
            sc -= 0.8
        scored.append((sc, i, s))
    top = sorted(scored, reverse=True)[:3]
    top = sorted(top, key=lambda x: x[1])
    out, total = [], 0
    for _, _, s in top:
        if total + len(s) > 560 and out:
            break
        out.append(s)
        total += len(s)
    return " ".join(out)


def clip(s, n):
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + " ..."


def pick_facts_and_watch(what, sents):
    used = what
    facts, watch = [], []
    for s in sents[:40]:
        if s in used:
            continue
        if len(watch) < 2 and WATCH.search(s):
            watch.append(clip(s, 200))
        elif NUM.search(s) and len(facts) < 5 and len(toks(s) & toks(what)) / max(len(toks(s)), 1) < 0.6:
            facts.append(clip(s, 190))
    return facts, watch


# ---------------------------------------------------------------- why it affects you (rules; edit freely)
IMPACT_POLICY = [
    (r"epfo|provident fund|wage ceiling|pension|\bnps\b|labour code|minimum wage",
     "Changes what salaried people and employers put into retirement schemes. Check the salary structures of your clients and your own PF deduction."),
    (r"\bgst\b|customs duty|import duty|export duty|anti-dumping|tariff|safeguard duty",
     "Changes costs and margins for the goods it covers. Review client holdings in those sectors and any dependence on imported inputs."),
    (r"repo|monetary policy|\bcrr\b|\bslr\b|liquidity|interest rate|treasury bill|g-sec|bond yield",
     "Moves bond yields and fixed-income fund values. Revisit duration and the debt allocation you run for clients."),
    (r"\bkyc\b|know your customer|re-kyc|anti-money",
     "A compliance change for banks and account holders. Clients may be asked to update KYC, so keep their documents current."),
    (r"sebi|mutual fund|\bpms\b|\baif\b|portfolio manager|investment advis|research analyst|stock exchange|disclosure|clearing",
     "Touches the rulebook for products you recommend and for your own advisory practice. Check what changes in disclosure, distribution or client onboarding."),
    (r"\brbi\b|reserve bank|\bbanks?\b|nbfc|lending|credit",
     "Affects lenders and borrowers. Watch bank and NBFC holdings in client portfolios and the pricing of loans."),
    (r"outlay|subsid|\bpli\b|incentive|mission|scheme|yojana",
     "Fiscal support for a sector. Look for listed beneficiaries, and note the cost to the government's deficit."),
    (r"free trade|trade agreement|\bfta\b|mercosur|export|import",
     "Opens or protects overseas markets. Matters for exporters and the currency; trade deals sometimes carry professional-mobility terms too."),
    (r"disinvest|privati[sz]|monetis|\bfdi\b|foreign direct|foreign investment",
     "Changes the supply of government assets or foreign-ownership limits. A valuation signal for PSU and foreign-owned names."),
    (r"railway|highway|nhai|\bports?\b|airport|infrastructure|metro|corridor",
     "Order-book news for rail, road and construction suppliers. A single small project rarely moves a stock."),
    (r"sugar|rice|wheat|pulses|food|fertili[sz]er|\bmsp\b|crop|agri",
     "Touches food prices and agri-linked sectors, which feed into inflation readings and the rate outlook."),
    (r"lpg|fuel|petrol|diesel|\boil\b|\bgas\b|power|electric|renewable|solar|coal",
     "Energy costs: affects household budgets, inflation, and oil-marketing and power stocks."),
    (r"semicon|semiconductor|electronics|telecom|spectrum|digital|data protection|\bai\b",
     "Technology policy: signals where the government wants capital to flow. See listed electronics and telecom names and startup funding in the area."),
    (r"aadhaar|\bdbt\b|welfare|beneficiar",
     "Changes how welfare reaches households; relevant to fiscal cost and household spending."),
]
IMPACT_STARTUP = {
    "IPO & Listing": "A listing to evaluate. The offer document (DRHP) discloses the revenue model, cash burn and risks, and the price sets a valuation comparison for similar businesses.",
    "Funding": "Shows where investors are putting money in {sector}. Use it as a valuation and competition reference and note who is backing the company.",
    "Financials": "A health check on the business model: growth against losses. Compare the numbers with listed peers and see how the company actually earns its revenue.",
    "Acquisition": "Consolidation in {sector}. It changes the competitive picture and can set an exit valuation for similar companies.",
    "Shutdown & Layoffs": "A warning signal. Look for the same business model or the same funding dependence in other startups you follow.",
    "Launch & Product": "A product or market expansion. Watch whether it adds a genuinely new revenue stream.",
    "Analysis": "Context for understanding the startup ecosystem in {sector}.",
}
IMPACT_IMM = [
    (r"salary|threshold|income requirement|pay limit|minimum wage",
     "A salary floor sets the minimum pay you must secure. Compare it with the pay for your target finance role."),
    (r"permanent residen|settlement|indefinite leave|\bilr\b|green card|long-term resident",
     "Changes your time to permanent residence, the number that decides whether a move is a 2-year or a 10-year commitment."),
    (r"citizenship|naturali[sz]ation",
     "Changes your citizenship clock. India does not allow dual citizenship, so taking a foreign passport means giving up the Indian one (an OCI card is the usual fallback)."),
    (r"quota|cap\b|levels plan|planning levels|ceiling",
     "Changes how many places exist, so it changes your odds more than the rules do."),
    (r"student|graduate|post-study",
     "Relevant only if you take the study-then-work route (a master's abroad). Otherwise background."),
    (r"skilled|work visa|work permit|blue card|employer|sponsor|talent",
     "Touches the work-visa route you would use as a skilled professional."),
    (r"election|party|referendum|vote|coalition|manifesto|parliament",
     "Political risk: rules can change after an election. Note the direction of the debate, not just today's law."),
]


def why_lines(desk, item, text, files, profile_urls):
    hay = f"{item['title']} {text[:1800]}".lower()
    out = []
    if desk == "Policy":
        for scope in (item["title"].lower(), hay):          # the headline decides first; the body only if the headline is silent
            for rx, line in IMPACT_POLICY:
                if re.search(rx, scope, re.I) and line not in out:
                    out.append(line)
                if len(out) == 2:
                    break
            if out:
                break
        if not out:
            out.append("Indirect for portfolios: a policy signal worth knowing, with no direct action for clients today.")
        cr = re.search(r"(?:Rs\.?|₹)\s?([\d,]+(?:\.\d+)?)\s?(lakh crore|crore)", hay, re.I)
        if cr:
            out.append(f"Scale: about Rs {cr.group(1)} {cr.group(2)} is involved, so gauge whether that is large against the sector it targets.")
    elif desk == "Startups":
        line = IMPACT_STARTUP.get(item.get("type", "Analysis"), IMPACT_STARTUP["Analysis"]).format(sector=item.get("sector", "this sector"))
        out.append(line)
        if re.search(r"fintech|lending|nbfc|payments?|upi|insurance", hay):
            out.append("Regulatory moves by RBI or SEBI hit this kind of business directly, so it is also a read on the Policy Desk.")
        if item.get("url") in profile_urls:
            out.append("A Startup File is written for this company: see how it makes money on the Startup Desk.")
        out.append("Lesson for your own work: note how the company prices and earns, which is useful for advisory conversations and content.")
    else:
        c = next((x for x in files.get("countries", []) if x["id"] == item.get("country")), None)
        if c:
            out.append(f"{c['name']} is on your 19-country shortlist. Your Country File reads: {c['trend']}.")
        matched = False
        for rx, line in IMPACT_IMM:
            if re.search(rx, hay, re.I):
                out.append(line)
                matched = True
                break
        if not matched:
            out.append("Background on the immigration climate; no specific rule change is stated in the article.")
        if re.search(r"\bindia\b|\bindians?\b", hay):
            out.append("It names India or Indian nationals, so it applies to you directly.")
        if c:
            pr = f"{c['prSort']} years" if c.get("prSort") not in (None, 0) else ("on arrival via points" if c.get("prSort") == 0 else "not verified yet")
            cit = f"{c['citSort']} years" if c.get("citSort") else "not verified yet"
            out.append(f"Your Country File clocks: permanent residence {pr}; citizenship {cit}.")
    return out[:4]


def verdict(desk, item, text, must):
    src = (item.get("source") or "") + " " + (item.get("ministry") or "")
    exact = bool(re.search(r"threshold|deadline|apply (?:by|before)|fee|form|from \d|effective|schedule|per cent|%", text[:2500], re.I))
    if desk == "Immigration" and item.get("official"):
        return "open", "Open it: this is an official notice and the exact wording matters."
    if desk == "Policy" and re.search(r"RBI|SEBI", src):
        return "worth", "Worth opening if this touches a client: regulator text is exact, and the original has the full clauses and dates."
    if desk == "Immigration" and must and exact:
        return "worth", "Worth opening if you plan to act on it: the original carries exact numbers, dates or conditions."
    if not text:
        return "worth", "The article could not be read automatically, so this brief is thin. Open the link for detail."
    return "skip", "You can skip the link: this brief covers the essentials."


# ---------------------------------------------------------------- optional AI path (off unless BRIEF_LLM_KEY is set)
def ai_brief(desk, item, text, ctx):
    key = os.environ.get("BRIEF_LLM_KEY")
    if not key or not text:
        return None
    provider = os.environ.get("BRIEF_LLM_PROVIDER", "anthropic").lower()
    prompt = (f"{PROFILE}\n\nSummarise this news story for him so he does not need to open the link. Return ONLY JSON with keys: "
              f'"what" (2-3 sentences: what happened), "facts" (list of up to 5 short factual bullets with numbers/dates), '
              f'"why" (list of 2-3 bullets on why it affects HIM specifically), "watch" (list of up to 2 next steps or deadlines). '
              f"Use only facts in the article. Desk: {desk}.\n\nTitle: {item['title']}\n\nArticle:\n{text[:7000]}")
    try:
        if provider == "anthropic":
            body = json.dumps({"model": os.environ.get("BRIEF_LLM_MODEL", "claude-haiku-4-5-20251001"), "max_tokens": 900,
                               "messages": [{"role": "user", "content": prompt}]}).encode()
            req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
                "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
            out = json.loads(urllib.request.urlopen(req, timeout=60).read())["content"][0]["text"]
        else:
            base = os.environ.get("BRIEF_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
            body = json.dumps({"model": os.environ["BRIEF_LLM_MODEL"], "messages": [{"role": "user", "content": prompt}]}).encode()
            req = urllib.request.Request(base + "/chat/completions", data=body, headers={
                "Authorization": f"Bearer {key}", "content-type": "application/json"})
            out = json.loads(urllib.request.urlopen(req, timeout=60).read())["choices"][0]["message"]["content"]
        data = json.loads(re.search(r"\{.*\}", out, re.S).group(0))
        return {"what": str(data["what"]), "facts": [str(x) for x in data.get("facts", [])][:5],
                "why": [str(x) for x in data.get("why", [])][:4], "watch": [str(x) for x in data.get("watch", [])][:2]}
    except Exception as e:  # noqa: BLE001
        print("  AI brief failed, using rule-based:", str(e)[:80], file=sys.stderr)
        return None


# ---------------------------------------------------------------- main
def make_brief(desk, item, text, files, profile_urls, must):
    fallback = item.get("summary") or item.get("blurb") or item["title"]
    text = re.sub(r"^\s*RBI/\d{4}-\d{2}/\d+\s+[A-Z][A-Za-z.\d/\-]*\s+", "", text or "")     # RBI circular reference header
    sents = split_sentences(text, item["title"]) if text else []
    ai = ai_brief(desk, item, text, files)
    if ai:
        what, facts, watch, why, method = ai["what"], ai["facts"], ai["watch"], ai["why"], "ai"
    else:
        what = pick_what(item["title"], sents) if sents else fallback
        facts, watch = pick_facts_and_watch(what, sents)
        why, method = why_lines(desk, item, text or fallback, files, profile_urls), "extractive"
    if desk == "Immigration":
        c = next((x for x in files.get("countries", []) if x["id"] == item.get("country")), None)
        if c and c.get("watch"):
            watch = (watch + [f"From your Country File: {c['watch'][0]}"])[:3]
    level, vtext = verdict(desk, item, text, must)
    return {"desk": desk, "title": item["title"], "what": what, "facts": facts, "why": why, "watch": watch,
            "level": level, "verdict": vtext, "method": method, "partial": not bool(sents),
            "built": datetime.now(IST).strftime("%Y-%m-%d")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=int, default=120, help="max article pages to fetch this run")
    ap.add_argument("--redo", action="store_true", help="rebuild briefs that already exist")
    ap.add_argument("--rewhy", action="store_true", help="re-run only the impact rules on stored briefs (no page fetches); use after editing IMPACT_*")
    args = ap.parse_args()

    briefs = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    files = load("immigration_files.json")
    profile_urls = {p["key"] for p in load("profiles.json").get("profiles", [])}
    front = load("front.json")
    must = {i["url"]: i.get("must_read") for i in front.get("items", [])}
    front_urls = [i["url"] for i in front.get("items", [])] + [i["url"] for d in front.get("desks", {}).values() for i in d["items"]]

    work = []                                           # (desk, item) in priority order
    by_url = {}
    for desk, fn in (("Policy", "items.json"), ("Startups", "startups.json"), ("Immigration", "immigration.json")):
        cutoff = (datetime.now(IST) - timedelta(days=IMM_DAYS)).strftime("%Y-%m-%d")
        for it in load(fn).get("items", []):
            if desk == "Immigration" and it["date"] < cutoff:
                continue
            by_url[it["url"]] = (desk, it)
    seen = set()
    for u in front_urls:                                # front page first
        if u in by_url and u not in seen:
            work.append(by_url[u]); seen.add(u)
    for u, pair in sorted(by_url.items(), key=lambda kv: kv[1][1]["date"], reverse=True):
        if u not in seen:
            work.append(pair); seen.add(u)

    if args.rewhy:
        n = 0
        for u, (desk, it) in by_url.items():
            b = briefs.get(u)
            if not b or b["method"] == "ai":
                continue
            proxy = " ".join([b["what"]] + b["facts"])
            b["why"] = why_lines(desk, it, proxy, files, profile_urls)
            b["level"], b["verdict"] = verdict(desk, it, proxy, must.get(u))
            n += 1
        OUT.write_text(json.dumps(briefs, ensure_ascii=False), encoding="utf-8")
        print(f"re-ran impact rules on {n} briefs")
        return

    fetched = made = 0
    for desk, it in work:
        if it["url"] in briefs and not args.redo:
            continue
        if fetched >= args.budget:
            break
        text = article_text(it["url"])
        fetched += 1
        time.sleep(0.3)
        briefs[it["url"]] = make_brief(desk, it, text, files, profile_urls, must.get(it["url"]))
        made += 1
        if made % 25 == 0:
            OUT.write_text(json.dumps(briefs, ensure_ascii=False), encoding="utf-8")
            print(f"  ...{made} briefs")
    # keep only briefs for stories still on file
    briefs = {u: b for u, b in briefs.items() if u in by_url}
    OUT.write_text(json.dumps(briefs, ensure_ascii=False), encoding="utf-8")
    partial = sum(1 for b in briefs.values() if b["partial"])
    print(f"{made} new briefs, {len(briefs)} on file ({partial} thin because the article could not be read); "
          f"{sum(1 for u in by_url if u not in briefs)} stories still waiting for a brief")


if __name__ == "__main__":
    main()
