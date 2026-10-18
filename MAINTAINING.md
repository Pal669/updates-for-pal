# Running Updates for Pal without any AI or the EA Demo system

This folder is the whole newspaper. Code, data and schedule all live here. Nothing outside it is needed.
Claude, agents and skills are optional helpers. If they vanish, nothing here stops working.

## What you need
- A copy of this repo (GitHub: Pal669/updates-for-pal, or this folder).
- Python 3 (standard library only) to run collectors by hand.
- A free GitHub account to keep the automatic refresh, or any static host if you leave GitHub.

## What runs on its own
GitHub Actions (`.github/workflows/update.yml`, `advisory.yml`) runs the collectors several times a day and commits the
data. Your PC and Mac do not need to be on. Check it under the repo's Actions tab; "Run workflow" forces a refresh.

## Run it by hand
    git pull --rebase
    python scripts/fetch_policies.py
    python scripts/fetch_startups.py
    python scripts/fetch_immigration.py
    python scripts/fetch_listed.py
    python scripts/company_intel.py
    python scripts/build_front_page.py
    python scripts/brief.py --budget 150
    python scripts/advisory_market.py
    python scripts/fetch_pms_aif.py --budget 90
    python scripts/fetch_advisory.py
    python -m http.server 8000        # preview at http://localhost:8000
    git add -A && git commit -m "data" && git pull --rebase && git push

## Monthly, by hand (not in Actions because they need `pip install pypdf`)
    python scripts/apmi_aum.py        # official PMS AUM
    python scripts/aif_cat3.py        # Category III AIF table

## Hand-written data (yours to edit in any text editor)
- `data/company_notes.json` Nifty 100 business descriptions
- `data/profiles.json` Startup Files
- `data/immigration_files.json` Country Files (dated facts, re-verify before relying on them)

## Moving to a different host
The site is static files. Copy the folder to any web host (Netlify, Cloudflare Pages, your own server). For the automatic
refresh elsewhere, run the "Run it by hand" commands from cron or Task Scheduler and publish the folder.

## Backups
The repo lives in three places: GitHub, this OneDrive folder, and any clone. Never delete `data/*.json`; existing items are
never dropped.

## After a front-end change
Bump the `?v=` number on app.js and style.css in `index.html`, or browsers show the old version.

## No AI
No script calls any AI model or needs any key. Briefs are rule-based (`scripts/brief.py`). Code is written with Claude's
help, but once written it runs on its own.
