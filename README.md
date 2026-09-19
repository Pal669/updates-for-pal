# Updates for Pal

A personal newspaper. Static site, hosted on GitHub Pages, refreshed by GitHub Actions.
No AI service, no API keys, no third-party libraries. Python standard library and plain HTML/CSS/JS only.
Move it anywhere: copy this folder to any static host and any machine with Python 3.

## Desks
- **Policy Desk** (live): new Government of India policy, from PIB (Cabinet decisions, ministry schemes, duties, subsidies,
  budget items), RBI (directions, circulars, policy releases) and SEBI (circulars, regulations, consultation papers).
  Each card = official headline + the government's own opening lines + link to the original.

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
