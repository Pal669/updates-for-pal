"""Official PMS AUM and client counts by portfolio manager -> data/pms_aum_official.json.

Source: APMI (Association of Portfolio Managers in India), "AUM & Client Count Data - PMS Level" PDF, which APMI
compiles from SEBI's monthly report. It is official, firm-level, and published monthly with a lag (the file names the
month it is "as on").

    python scripts/apmi_aum.py

This is the ONE script in the repo that is not standard-library only: reading a PDF needs `pypdf` (pip install pypdf).
That is why it is not part of the GitHub Actions run. Run it by hand once a month (or ask Claude to). Everything else
in the paper keeps working without it, and the page shows the "as on" date so a stale file is visible.
"""
import json, re, sys, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "pms_aum_official.json"
IST = timezone(timedelta(hours=5, minutes=30))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
BASE = "https://www.apmiindia.org"


def get(url, binary=False):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
        b = r.read()
    return b if binary else b.decode("utf-8", "replace")


def latest_pdf_url():
    home = get(BASE + "/")
    links = re.findall(r'href="(/storagebox/images/Important/[^"]*AUM[^"]*Client Count[^"]*PMS Level[^"]*\.pdf)"', home, re.I)
    if not links:
        raise SystemExit("could not find the PMS-level AUM PDF link on apmiindia.org")

    def fy(u):      # 'FY 26-27' -> 26 so the newest financial year wins
        m = re.search(r"FY\s*(\d\d)-(\d\d)", u)
        return int(m.group(1)) if m else 0
    best = max(links, key=fy)
    return BASE + urllib.parse.quote(best, safe="/:")


def main():
    try:
        import pypdf
    except ImportError:
        raise SystemExit("pypdf is needed for this step: pip install pypdf")
    url = latest_pdf_url()
    tmp = ROOT / "data" / "_apmi_tmp.pdf"
    tmp.write_bytes(get(url, binary=True))
    reader = pypdf.PdfReader(str(tmp))
    text = "\n".join(p.extract_text() for p in reader.pages)
    tmp.unlink()
    m = re.search(r"As on\s+(\d{2})\.(\d{2})\.(\d{4})", text)
    as_on = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None
    rx = re.compile(r"^(?P<name>.+?)\s*(?P<reg>INP\d{9})\s+(?P<date>\d{2}-\d{2}-\d{4})\s+(?P<clients>\d+)\s+(?P<aum>[\d,]+\.\d+)\s*$")
    firms = []
    for line in text.splitlines():
        mm = rx.match(line.strip())
        if mm:
            firms.append({"name": mm.group("name").strip(), "reg": mm.group("reg"), "registered": mm.group("date"),
                          "clients": int(mm.group("clients")), "aum_cr": float(mm.group("aum").replace(",", ""))})
    if len(firms) < 100 or not as_on:
        raise SystemExit(f"parse looks wrong ({len(firms)} firms, as_on={as_on}); not overwriting the file")
    ref = datetime.strptime(as_on, "%Y-%m-%d")
    for f in firms:        # flag figures a reader should not take at face value; nothing is removed or corrected
        reg = datetime.strptime(f["registered"], "%d-%m-%Y")
        if f["clients"] <= 5 and f["aum_cr"] >= 10000:
            f["flag"] = "Very few clients but very large AUM: usually an institutional (EPFO / provident fund) mandate, or an error in the source. Treat with care."
        elif (ref - reg).days < 365 and f["aum_cr"] >= 1000:
            f["flag"] = "Registered within the last year but shows large AUM. Check the source."
    total = round(sum(f["aum_cr"] for f in firms), 2)
    OUT.write_text(json.dumps({"as_on": as_on, "fetched": datetime.now(IST).strftime("%Y-%m-%d"), "source": "APMI, compiled from SEBI's monthly report",
                               "source_url": url, "count": len(firms), "total_aum_cr": total, "total_clients": sum(f["clients"] for f in firms),
                               "firms": sorted(firms, key=lambda f: -f["aum_cr"])}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(firms)} portfolio managers, as on {as_on}, total AUM Rs {total:,.2f} Cr, clients {sum(f['clients'] for f in firms):,}")


if __name__ == "__main__":
    main()
