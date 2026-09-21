"""Investment Advisory Universe: PMS and AIF strategy data -> data/pms_aif.json.

Python standard library only, no API keys, no AI, no rewriting: every figure is copied from the source page and every
card links back to it.

    python scripts/fetch_pms_aif.py              # refresh the stalest pages, up to --budget (default 90) per run
    python scripts/fetch_pms_aif.py --all        # refresh everything (about 500 pages, ~5 minutes)

Sources
  PMS AIF World (pmsaifworld.com)   one public page per PMS / AIF strategy: manager, experience, inception, corpus,
                                    benchmark, trailing returns (1M ... since inception) vs the benchmark, standard
                                    deviation, share of positive months, and the "returns as of" date. The list of
                                    strategies comes from the site's own sitemap.
  PMS Bazaar (pmsbazaar.com)        the public top-performers leaderboard on the home page (1M / 1Y / 3Y / 5Y).
Official AUM by portfolio manager (APMI / SEBI) is a separate file: scripts/apmi_aum.py.

Honest limits, repeated on the page: PMS returns are published monthly and AIF returns quarterly or irregularly, so a
daily run only picks up changes when the aggregator updates. Returns up to 1 year are absolute, beyond 1 year CAGR.
Aggregator numbers are as reported by the aggregator, not audited by this newspaper. Not investment advice.
"""
import html, json, re, sys, time, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "pms_aif.json"
IST = timezone(timedelta(hours=5, minutes=30))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
SITEMAP = "https://www.pmsaifworld.com/portfolio-sitemap.xml"
REFRESH_DAYS = 6
DELAY = 0.35            # seconds between page fetches: polite to a small site
STOPW = {"pms","aif","fund","portfolio","strategy","the","and","ltd","limited","asset","management","company","series","category","investment","managers","advisors","capital","amc","llp","pvt","private","equity","opportunities","scheme"}
PERIODS = ["1m", "3m", "6m", "1y", "2y", "3y", "5y", "10y", "si"]


def get(url, timeout=45, tries=3):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise last


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or "")).replace("\xa0", " ")).strip()


def num(s):
    s = (s or "").replace("%", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def month_end(text):
    """'31st Aug 2026' or '31 August 2026' -> 2026-08-31"""
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})", text or "")
    if not m:
        return None
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def kind_of(slug, title, text):
    hay = f"{slug} {title}".lower()
    m = re.search(r"category[- ]?(iii|ii|i)\b|cat[- ]?(iii|ii|i)\b", hay) or re.search(r"Category of the Fund:\s*CATEGORY\s*-?\s*(III|II|I)\b", text, re.I)
    if m:
        c = next(g for g in m.groups() if g).upper()
        return f"AIF Cat {c}"
    if re.search(r"\baif\b", hay):
        return "AIF"
    if "pms" in hay or "Number of Stocks" in text or "Portfolio Manager" in text:
        return "PMS"
    return "PMS / AIF"


def table_rows(block):
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", block, re.S | re.I):
        cells = [clean(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        if cells:
            rows.append(cells)
    return rows


def field(text, *labels):
    for lab in labels:
        m = re.search(re.escape(lab) + r"\s*:?\s*(.+?)(?=\s+(?:Portfolio Manager|Fund Manager|Inception Date|Number of Stocks|Minimum|Type:|Fund Structure|Category of|Investment (?:Objective|Strategy|Philosophy)|Portfolio Strategy|Fund Theme|Performance Table|Key Portfolio)|$)", text)
        if m and m.group(1).strip():
            return m.group(1).strip()[:160]
    return None


def parse(page, url):
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    title = clean((re.search(r"<title>(.*?)</title>", page, re.S | re.I) or [None, ""])[1])
    title = re.sub(r"\s*[-|]\s*PMS AIF WORLD.*$", "", title, flags=re.I).strip()
    m = re.search(r"Key Portfolio Attributes(.*?)(?:Investment Objective|Investment Strategy|Portfolio Strategy|Fund Theme|Performance Table|$)", clean(page), re.S)
    attrs = m.group(1) if m else ""
    body = clean(re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S | re.I))
    rec = {"slug": slug, "url": url, "title": title, "kind": kind_of(slug, title, body), "source": "PMS AIF World"}

    rec["manager"] = field(attrs, "Portfolio Manager's Name", "Portfolio Manager’s Name", "Fund Manager's Name", "Fund Manager’s Name", "Fund Manager Name", "Fund Manager")
    rec["experience"] = field(attrs, "Portfolio Manager's Experience", "Portfolio Manager’s Experience")
    rec["inception_text"] = field(attrs, "Inception Date")
    rec["stocks_text"] = field(attrs, "Number of Stocks")
    rec["ticket"] = field(attrs, "Minimum Ticket Size")
    rec["structure"] = field(attrs, "Fund Structure")
    rec["fund_type"] = field(attrs, "Type")

    # trailing returns table: [label, 1m ... si] for the strategy, then the benchmark
    tm = re.search(r'<table class="portfolio_performance_table">(.*?)</table>', page, re.S | re.I)
    rec["ret"], rec["bench_ret"], rec["bench"], rec["label"] = {}, {}, None, None
    if tm:
        rows = table_rows(tm.group(1))
        head = [h.lower() for h in rows[0]] if rows else []
        cols = [i for i, h in enumerate(head) if "return" in h and i > 0]
        if len(rows) >= 2 and len(cols) == len(PERIODS) and len(rows[1]) > max(cols):
            rec["label"] = rows[1][0]
            rec["ret"] = {p: num(rows[1][c]) for p, c in zip(PERIODS, cols)}
            if len(rows) >= 3 and len(rows[2]) > max(cols):
                rec["bench"] = rows[2][0]
                rec["bench_ret"] = {p: num(rows[2][c]) for p, c in zip(PERIODS, cols)}
    # QRC report card: strategy, category, manager, inception, age, corpus, benchmark, SI, stocks, sectors
    qm = re.search(r'id="qrc_data".*?<tbody>(.*?)</tbody>', page, re.S | re.I)
    rec["category"], rec["corpus_cr"], rec["inception"], rec["age"], rec["stocks"] = None, None, None, None, None
    if qm:
        rows = [r for r in table_rows(qm.group(1)) if len(r) >= 9]
        if rows:
            r = rows[0]
            rec["category"] = r[1] or None
            if r[2]:
                rec["manager"] = r[2]          # the report-card cell is cleaner than the free-text attribute
            rec["inception_text"] = rec["inception_text"] or r[3]
            rec["age"] = r[4] or None
            rec["corpus_cr"] = num(r[5])
            rec["bench"] = rec["bench"] or r[6]
            rec["stocks"] = int(r[8]) if r[8].isdigit() else None
    rec["inception"] = month_end(rec.get("inception_text") or "")

    st = re.search(r"Alpha \(1Y\)\s+Beta \(1Y\)\s+Standard Deviation \(1Y\)\s+% of \+ve Months \(SI\)\s+(-?[\d.]+)%\s+(-?[\d.]+)\s+(-?[\d.]+)%\s+(-?[\d.]+)%", body)
    rec["sd_1y"] = num(st.group(3)) if st else None
    rec["pos_months"] = num(st.group(4)) if st else None
    ao = re.search(r"Returns as of\s+([^.]{4,30}?\d{4})", body, re.I)
    rec["as_of"] = month_end(ao.group(1)) if ao else None
    rec["has_returns"] = any(v is not None for v in rec["ret"].values())
    # The returns table names the strategy its numbers belong to. When that name shares no distinctive words with the page
    # title (the aggregator has re-used a page), the returns are shown under the table's name and the mismatch is flagged.
    rec["name"] = rec["label"] or title
    derive(rec)
    return rec


def derive(rec):
    """Fields computed from what was already copied from the page (kept separate so old records can be re-derived)."""
    rec["name"] = rec.get("label") or rec.get("title")

    def words(t, skip):   # distinctive words: drop the firm's brand words (first two words of the title), filler and short words
        return {w for w in re.findall(r"[a-z0-9]+", (t or "").lower()) if len(w) > 2 and w not in STOPW and w not in skip}
    skip = set(re.findall(r"[a-z0-9]+", (rec.get("title") or "").lower())[:2])
    a, b = words(rec.get("label"), skip), words(rec.get("title"), skip)
    rec["label_mismatch"] = bool(rec.get("label")) and bool(a) and bool(b) and not (a & b)
    m = rec.get("manager")
    if m:
        m = re.sub(r"^[\u2018\u2019']?s?\s*(?:Name)?\s*:\s*", "", m).strip()
        # a sentence or a different field, not a name: the page's layout differs, so better none than wrong
        if len(m) > 90 or re.search(r"\d|experience|years|founder|analyst|\bName\b|qualif|joined|managing|head of", m, re.I) or not re.match(r"^[A-Z]", m):
            m = None
    if m:
        m = re.sub(r"\b(Mr|Ms|Mrs|Dr)\.(?=[A-Z])", r"\1. ", m)
        m = re.sub(r"(?<![A-Za-z])(?:Mr|Ms|Mrs|Dr)\.?\s+", "", m).strip()
    rec["manager"] = m
    return rec


def sitemap_urls():
    s = get(SITEMAP)
    return re.findall(r"<loc>(https://www\.pmsaifworld\.com/portfolio/[^<]+)</loc>", s)


def bazaar_top():
    """PMS Bazaar's public top-performers boxes on its performance page: name, category, return, per period."""
    page = get("https://www.pmsbazaar.com/pms-performance")
    out = []
    labels = {"1": "1M", "2": "1Y", "3": "3Y", "4": "5Y"}
    for n, lab in labels.items():
        m = re.search(r'id="perftabs-%s">(.*?)(?=id="perftabs-\d"|$)' % n, page, re.S)
        if not m:
            continue
        for e in re.findall(r'<div class="entry col-12 py-1">(.*?)</div>\s*</div>\s*</div>\s*</div>', m.group(1), re.S) or re.findall(r'perf-strategy-name.*?</h4>.*?<h4 class="text-smaller">[^<]*</h4>', m.group(1), re.S):
            nm = re.search(r'perf-strategy-name"><a href="([^"]+)"[^>]*>(.*?)</a>', e, re.S)
            cat = re.search(r"<li>(.*?)</li>", e, re.S)
            val = re.findall(r'<h4 class="text-smaller">\s*(-?[\d.]+)%\s*</h4>', e)
            if nm and val:
                out.append({"period": lab, "name": clean(nm.group(2)), "category": clean(cat.group(1)) if cat else None, "ret": float(val[-1]),
                            "url": "https://www.pmsbazaar.com" + nm.group(1)})
    return out


def main():
    budget = 10 ** 6 if "--all" in sys.argv else 90
    if "--budget" in sys.argv:
        budget = int(sys.argv[sys.argv.index("--budget") + 1])
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"strategies": {}}
    strat = old.get("strategies", {})
    now = datetime.now(IST)
    stamp = now.strftime("%Y-%m-%d")

    try:
        urls = sitemap_urls()
    except Exception as e:  # noqa: BLE001
        print(f"sitemap failed: {e}", file=sys.stderr)
        urls = [v["url"] for v in strat.values()]
    known = {u.rstrip("/").rsplit("/", 1)[-1]: u for u in urls}
    for slug, u in known.items():          # keep every strategy already on file even if the sitemap drops it
        strat.setdefault(slug, {"slug": slug, "url": u, "fetched": "0000"})
    cutoff = (now - timedelta(days=REFRESH_DAYS)).strftime("%Y-%m-%d")
    due = sorted((v for v in strat.values() if v.get("fetched", "0000") < cutoff), key=lambda v: v.get("fetched", "0000"))[:budget]
    print(f"{len(known)} strategies in sitemap, {len(strat)} on file, {len(due)} to fetch this run")
    ok = bad = 0
    for v in due:
        try:
            rec = parse(get(v["url"]), v["url"])
            if not rec["title"]:
                raise ValueError("empty page")
            rec["fetched"] = stamp
            strat[v["slug"]] = rec
            ok += 1
        except Exception as e:  # noqa: BLE001
            bad += 1
            v["fetched"] = v.get("fetched", "0000")
            print(f"  {v['slug']}: {e}", file=sys.stderr)
        time.sleep(DELAY)

    bz = old.get("bazaar_top", [])
    try:
        got = bazaar_top()
        if got:
            bz = got
    except Exception as e:  # noqa: BLE001
        print(f"PMS Bazaar leaderboard failed: {e}", file=sys.stderr)

    for v in strat.values():
        if v.get("title"):
            derive(v)
    fetched_ok = [v for v in strat.values() if v.get("title")]
    if not fetched_ok:
        print("nothing usable; keeping the previous file", file=sys.stderr)
        return
    latest = max((v["as_of"] for v in fetched_ok if v.get("as_of")), default=None)
    OUT.write_text(json.dumps({"updated": now.strftime("%Y-%m-%d %H:%M IST"), "returns_as_of": latest, "bazaar_top": bz, "bazaar_fetched": stamp,
                               "strategies": strat}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"fetched {ok} ok, {bad} failed; {len(fetched_ok)} strategies usable; latest returns as of {latest}; PMS Bazaar rows {len(bz)}")


if __name__ == "__main__":
    main()
