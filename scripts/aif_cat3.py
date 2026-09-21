"""Category III AIF performance tables -> data/aif_cat3.json.

Source: PMS AIF World's monthly "CAT 3 AIF Portfolios Performance Newsletter" (a PDF linked from a public blog post).
It ranks Long Only and Long Short Category III AIFs by 1M / 3M / 6M / 1Y / 3Y / 5Y / since-inception return, with
inception month and AUM where reported. Each row carries a marker for how the return is measured (post expenses and tax,
pre-tax, gross ...), and the markers differ from fund to fund, so rows are NOT strictly like-for-like. The page shows the
marker on every row and the source's own legend.

    python scripts/aif_cat3.py

Like apmi_aum.py this needs `pypdf` (pip install pypdf) and is run by hand once a month, after the newsletter appears
(early in the month). It is not part of the GitHub Actions run, which stays standard-library only. The page shows the
"as of" date, so a stale file is visible.
"""
import json, re, sys, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "aif_cat3.json"
IST = timezone(timedelta(hours=5, minutes=30))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
PERIODS = ["1m", "3m", "6m", "1y", "3y", "5y", "si"]
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}


def get(url, binary=False):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
        b = r.read()
    return b if binary else b.decode("utf-8", "replace")


def latest_post():
    sm = get("https://www.pmsaifworld.com/post-sitemap.xml")
    urls = re.findall(r"<loc>(https://www\.pmsaifworld\.com/blog/([a-z]+)-(20\d\d)-cat-3-aif-portfolios-performance-newsletter/)</loc>", sm)
    if not urls:
        raise SystemExit("no Cat III newsletter post found in the sitemap")
    best = max(urls, key=lambda u: (int(u[2]), MONTHS.get(u[1].capitalize(), 0)))
    return best[0], f"{best[1].capitalize()} {best[2]}"


def num(tok):
    tok = tok.strip()
    if tok in ("–", "-", "—", ""):
        return None
    return float(tok.replace("%", "").replace(",", ""))


ROW = re.compile(r"^(?P<name>.+?)\s+(?P<inc>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4})\s+(?P<aum>–|[\d,]+(?:\.\d+)?)\s+(?P<vals>(?:(?:–|-?\d+(?:\.\d+)?%)\s*){7})$")


def main():
    try:
        import pypdf
    except ImportError:
        raise SystemExit("pypdf is needed for this step: pip install pypdf")
    page_url, label = latest_post()
    page = get(page_url)
    pdfs = re.findall(r'href="(https://www\.pmsaifworld\.com/wp-content/uploads/[^"]*CAT-3-AIF[^"]*\.pdf)"', page, re.I)
    if not pdfs:
        raise SystemExit("newsletter PDF link not found on " + page_url)
    tmp = ROOT / "data" / "_cat3_tmp.pdf"
    tmp.write_bytes(get(pdfs[0], binary=True))
    reader = pypdf.PdfReader(str(tmp))
    text = "\n".join(p.extract_text() for p in reader.pages)
    tmp.unlink()
    text = re.sub(r"-\n(\d)", r"-\1", text)      # a negative number split across two lines: "-\n10.8%"
    ao = re.search(r"Returns as of\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s+(\d{4})", text)
    as_of = datetime.strptime(f"{ao.group(1)} {ao.group(2)} {ao.group(3)}", "%d %B %Y").strftime("%Y-%m-%d") if ao else None
    legend = re.search(r"(\^ Post Exp & Tax.*?Pre Perf\. Fees\.)", re.sub(r"\s+", " ", text))
    basis_note = re.search(r"Returns up to 1 year are Absolute[^.]*\.[^.]*\.[^.]*\.", re.sub(r"\s+", " ", text))
    section, funds, loose = None, [], 0
    for raw in text.splitlines():
        line = raw.strip()
        if re.match(r"^Long Only CAT 3 AIF Performance", line):
            section = "Long Only"
            continue
        if re.match(r"^Long Short CAT 3 AIF Performance", line):
            section = "Long Short"
            continue
        if not section:
            continue
        if re.search(r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4}\s+(?:–|[\d,.]+)\s+", line) and "Returns as of" not in line:
            loose += 1
        m = ROW.match(line)
        if not m:
            continue
        name = m.group("name").strip()
        mk = re.search(r"(\^|\*\*|\*|##|#)+$", name)
        basis = mk.group(0) if mk else ""
        name = name[: len(name) - len(basis)].strip() if basis else name
        vals = [v for v in re.split(r"\s+", m.group("vals").strip())]
        if len(vals) != 7:
            continue
        funds.append({"name": name, "basis": basis, "section": section, "inception": m.group("inc"),
                      "aum_cr": None if m.group("aum") == "–" else float(m.group("aum").replace(",", "")),
                      "ret": dict(zip(PERIODS, [num(v) for v in vals]))})
    # every line that looks like a data row must have parsed; anything else means the layout changed
    if not funds or abs(loose - len(funds)) > 2:
        raise SystemExit(f"parse check failed: {len(funds)} parsed vs {loose} row-like lines; not overwriting the file")
    OUT.write_text(json.dumps({"as_of": as_of, "edition": label, "fetched": datetime.now(IST).strftime("%Y-%m-%d"), "page_url": page_url, "pdf_url": pdfs[0],
                               "legend": legend.group(1).replace("Pe rf", "Perf") if legend else "^ Post Exp & Tax | * Post Exp, Pre Tax | # Gross | ** Post Exp, Pre Perf. Fees & Tax | ## Post Exp & Tax, Pre Perf. Fees",
                               "basis_note": basis_note.group(0) if basis_note else "Returns up to 1 year are absolute, above 1 year CAGR.",
                               "count": len(funds), "funds": funds}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    lo = sum(1 for f in funds if f["section"] == "Long Only")
    print(f"{label}: {len(funds)} Cat III AIFs ({lo} long only, {len(funds) - lo} long short), returns as of {as_of}; row-like lines seen {loose}")


if __name__ == "__main__":
    main()
