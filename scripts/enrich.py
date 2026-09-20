"""Fetch a picture and a longer snippet for a story link (used by build_front_page.py).

Python standard library only. Results are cached in data/enrich_cache.json so each link is fetched once.
  - image  : the article's own social-preview picture (og:image); PIB releases use the first photo in the release.
  - desc   : the publisher's description of the story (og:description)
  - lead   : the first paragraph or two of the article, trimmed (a snippet only; the card links to the full story)
Google News links are first resolved to the publisher's real URL.
Anything that fails is simply left empty; the page then shows a coloured tile instead of a picture.
"""
import html, json, re, time, urllib.parse, urllib.request
from datetime import datetime, timedelta
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / "data" / "enrich_cache.json"
UA = {"User-Agent": "Mozilla/5.0 (updates-for-pal)"}
BAD_IMG = re.compile(r"logo|emblem|favicon|default|placeholder|sprite|avatar|icon|googleusercontent\.com/J6_|/g\.gif|blank", re.I)
BOILER = re.compile(r"subscribe|sign up|newsletter|cookie|all rights reserved|follow us|read also|also read|advertisement|"
                    r"listen to this|click here|download the app|copyright|disrupt 20\d\d|% off|tickets|save up to|register now|exhibit|"
                    r"add as a (?:reliable|preferred)|trusted news source|catch all the", re.I)


def http(url, data=None, headers=None, timeout=15):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})}, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(1_500_000).decode("utf-8", "replace"), r.geturl()


def resolve_google(url):
    """news.google.com/rss/articles/<id> -> the publisher's URL (uses Google's own web endpoint; no key)."""
    try:
        gid = url.split("/articles/")[1].split("?")[0]
        page, _ = http(f"https://news.google.com/rss/articles/{gid}?hl=en-US&gl=US&ceid=US:en")
        sg = re.search(r'data-n-a-sg="([^"]+)"', page)
        ts = re.search(r'data-n-a-ts="([^"]+)"', page)
        if not (sg and ts):
            return None
        inner = json.dumps(["garturlreq", [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1],
                                          "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0], gid, int(ts.group(1)), sg.group(1)])
        body = urllib.parse.urlencode({"f.req": json.dumps([[["Fbv4je", inner, None, "generic"]]])}).encode()
        out, _ = http("https://news.google.com/_/DotsSplashUi/data/batchexecute", data=body,
                      headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
        m = re.search(r'\\"(https?://[^\\"]+)\\"', out)
        return m.group(1).replace("\\u003d", "=").replace("\\u0026", "&") if m else None
    except Exception:  # noqa: BLE001
        return None


def meta(page, key):
    for pat in (r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]*content=["\']([^"\']*)',
                r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']%s["\']'):
        m = re.search(pat % re.escape(key) if "%s" in pat else pat, page, re.I)
        if m and m.group(1).strip():
            return html.unescape(m.group(1)).strip()
    return None


def clean_text(s):
    s = re.sub(r"<(script|style|figure|aside|nav|footer).*?</\1>", " ", s, flags=re.S | re.I)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def lead_paragraphs(page, limit=440):
    m = re.search(r"<article.*?</article>", page, re.S | re.I)
    chunk = m.group(0) if m else page
    out, total = [], 0
    for p in re.findall(r"<p[^>]*>(.*?)</p>", chunk, re.S | re.I):
        t = clean_text(p)
        if len(t) < 70 or BOILER.search(t):
            continue
        out.append(t)
        total += len(t)
        if total >= limit or len(out) >= 3:
            break
    text = " ".join(out)
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + " ..."
    return text


def good_image(src, base):
    if not src:
        return None
    src = re.sub(r"^(https?):/(?!/)", r"\1://", src)          # 'https:/x' -> 'https://x'
    src = urllib.parse.urljoin(base, src)
    if BAD_IMG.search(src) or not src.startswith("http"):
        return None
    return src


def fetch_meta(url):
    real = url
    if "news.google.com" in url:
        real = resolve_google(url)
        if not real:
            return {}
    try:
        page, final = http(real)
    except Exception:  # noqa: BLE001
        return {"final_url": real}
    image = good_image(meta(page, "og:image") or meta(page, "twitter:image"), final)
    if "pib.gov.in" in final:
        image = None      # PIB pages carry only site banners, no per-release photo
    desc = meta(page, "og:description") or meta(page, "description") or ""
    if re.search(r"comprehensive, up-to-date news|subscribe to|sign in", desc, re.I):
        desc = ""
    return {"final_url": final, "image": image, "desc": desc[:340], "lead": lead_paragraphs(page)}


def load_cache():
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def save_cache(cache):
    cutoff = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d")
    cache = {k: v for k, v in cache.items() if v.get("_at", "9") >= cutoff}
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def enrich(url, cache, budget):
    """Return meta for url. Uses the cache; only fetches while budget['n'] > 0. Failed lookups are retried next day."""
    today = datetime.now().strftime("%Y-%m-%d")
    hit = cache.get(url)
    if hit and (hit.get("image") or hit.get("desc") or hit.get("_at") == today):
        return hit
    if budget["n"] <= 0:
        return hit or {}
    budget["n"] -= 1
    data = fetch_meta(url)
    data["_at"] = today
    cache[url] = data
    time.sleep(0.4)
    return data
