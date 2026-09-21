# Updates for Pal

A personal newspaper. Static site, hosted on GitHub Pages, refreshed by GitHub Actions.
No AI service, no API keys, no third-party libraries. Python standard library and plain HTML/CSS/JS only.
Move it anywhere: copy this folder to any static host and any machine with Python 3.

## Desks
- **Policy Desk** (live): new Government of India policy, from PIB (Cabinet decisions, ministry schemes, duties, subsidies,
  budget items), RBI (directions, circulars, policy releases) and SEBI (circulars, regulations, consultation papers).
  Each card = official headline + the government's own opening lines + link to the original.

- **Listed Universe** (India's Listed Market Universe): news on listed companies, in two sections. **Nifty 100** = the
  100 companies in NSE's official list (refreshed each run into `data/nifty100.json`). **All Other Companies** = every other
  NSE/BSE-listed company. Sources: NSE and BSE corporate announcements (the company's own filing, exchange one-line summary,
  PDF link), press RSS (ET, Business Standard, Mint, BusinessLine, Moneycontrol) and one Google News search per Nifty 100
  company. `scripts/fetch_listed.py` drops routine paperwork (AGM notices, trading window, ESOP, SAST stake disclosures) and
  sorts the rest into Results, Deals & M&A, Orders, Capital Raising, Payouts, Management, Ratings, Legal & Regulatory,
  Operations & Risk, Business Updates and Market Alerts. Tune `FILING_RULES`, `DROP_DESC`, `PRE_DROP`, `MATERIAL`
  (filings), `PRESS_RULES`, `MARKET_NOISE`, `FOREIGN` (press) and `MANUAL` (how a Nifty 100 company is spotted in a
  headline) at the top of the script. Keeps 30 days / 4,000 items. Not on the Front Page yet.
  Every card also carries a **company snapshot** and an **impact check**. `scripts/company_intel.py` pulls each company's
  revenue, net profit or loss, operating and free cash flow, debt and market value from Yahoo Finance (NSE companies) and Screener.in (BSE-only companies, and any company Yahoo lacks) into
  `data/companies.json` (Nifty 100 weekly; every other company in the desk when first seen, up to 400 per run, re-read after 30 days; a company with no data anywhere is retried weekly). Press headlines are tied to any NSE-listed company by name using NSE's full list (`data/nse_equity.json`); headlines about no listed company are dropped.
  "What it does / how it makes money / kind of business" for the Nifty 100 is hand-written in `data/company_notes.json`;
  other companies use their public profile and a "typical for this kind of business" line (the `MODELS` table in `app.js`).
  Impact = the rupee amount in the filing or headline (when one is stated) compared with revenue, profit or market value by
  fixed thresholds in `assess()`; when no amount is stated it says so. It is a size check, not a forecast.

## Investment Advisory Universe desk
Built for an investment advisor: numbers first, then PMS, AIF, debt and regulation, all with sources. No commentary.
Sections (sub-nav): Market Pulse, PMS, AIF, Debt & Bonds, Gold Silver & REITs, Mutual Funds, Regulatory, Global, All News.
- `scripts/advisory_market.py` -> `data/advisory_market.json`. NSE index feed (indices, sector indices, P/E, breadth, FII/DII),
  Yahoo Finance (global markets, US yields, dollar, gold, silver, crude, USD/INR, REIT/InvIT prices on BSE tickers), RBI
  homepage (policy rates), TradingView (India 10Y, best effort). Futures rows are continuous front-month: a 1D change can be a roll.
- `scripts/fetch_pms_aif.py` -> `data/pms_aif.json`. One public PMS AIF World page per strategy (list from their sitemap):
  manager, corpus, category, benchmark, trailing returns, "as of" date. Refreshes the stalest 90 pages a run (`--all` for all).
  A returns table that names a different strategy from the page title is flagged "check source". PMS Bazaar's public
  top-performers leaderboard is kept alongside as a second source.
- `scripts/fetch_advisory.py` -> `data/advisory.json`. News: RSS from ET, Mint, Business Standard, BusinessLine, CNBC-TV18, CNBC,
  BBC, MarketWatch + Google News searches, sorted into one category by the regex tables at the top; SEBI/RBI/finance-ministry
  items are copied from `data/items.json`. Nothing is summarised.
- Monthly, by hand (need `pip install pypdf`, so NOT in Actions): `scripts/apmi_aum.py` -> `data/pms_aum_official.json`
  (official PMS AUM and clients by portfolio manager, APMI/SEBI; suspicious rows are flagged, not hidden) and
  `scripts/aif_cat3.py` -> `data/aif_cat3.json` (Category III AIF performance table; the return basis marker per fund is shown).
- Refresh: `.github/workflows/advisory.yml`, once a day at 18:30 IST after the close (plus a 19:45 backup). Front Page takes up to
  5 Advisory stories (`score_advisory` in `build_front_page.py`).

## How it works
- `scripts/fetch_policies.py` reads the official feeds, keeps items whose title announces an action (see `ACTION` and
  `NOISE_TITLE` in the script), tags a sector, and merges them into `data/items.json`. Existing items are never lost.
- `index.html`, `style.css`, `app.js` render `data/items.json`.
- `.github/workflows/update.yml` runs the script at 08:00 and 22:00 IST and commits any new items.
  PIB's listing page only shows the current day, hence the late-evening run.

## Run it by hand
    python scripts/fetch_policies.py                 # add what is new
    python scripts/fetch_policies.py --backfill 14   # also read the last 14 days of PIB
    python -m http.server 8000                       # preview at http://localhost:8000

## Tuning what shows up
Edit the regular expressions at the top of `scripts/fetch_policies.py`:
`ACTION` (must match to be kept), `NOISE_TITLE` (always dropped), `SECTORS`, `MAJOR` (flags a card as a major decision).

## Adding a desk
Add a collector function in `scripts/` that writes its own `data/<desk>.json`, add a nav link in `index.html`, and a
renderer in `app.js`. The policy desk is untouched by that.

## Front Page and schedule
`scripts/build_front_page.py` picks the 15-20 highest-priority stories across the three desks into `data/front.json`
(rule-based points, listed on each card as "Why it is here"). The GitHub Actions workflow rebuilds everything at about
05:17, 05:37 and 06:07 IST (three tries because GitHub's scheduler sometimes runs late or skips), plus 16:07 and 22:07 IST
to catch PIB, which only lists the current day. The page shows a warning if the last refresh is more than 30 hours old.

## Front Page design
Hero story with picture and a longer snippet, four feature cards, a rotating Startup File and Country Spotlight, a market
snapshot (Nifty, Sensex, USD/INR, Brent, gold, US 10Y from Yahoo Finance), the remaining ranked headlines with thumbnails,
and a snapshot column per desk. "Choose your interest" filters the whole page by desk or topic (`#top/Startups` opens on one).
`scripts/enrich.py` fetches each story's own preview picture and opening lines (cached in `data/enrich_cache.json`); where a
site offers no picture (PIB, RBI, SEBI) the page shows a coloured tile. Everything stays clickable and opens the original.

## Briefs
`scripts/brief.py` reads each story's full text and writes a brief into `data/briefs.json`: what happened, key facts,
why it affects you, what to watch, and whether the original is worth opening. Default mode is rule-based (it extracts the
article's own sentences and maps the story onto the profile and the Country Files with the `IMPACT_*` tables in the script).
To upgrade to real comprehension, add an AI provider key as the repository secret `BRIEF_LLM_KEY` (and variables
`BRIEF_LLM_PROVIDER` = anthropic or openai, `BRIEF_LLM_MODEL`). Without a key nothing external is called.
