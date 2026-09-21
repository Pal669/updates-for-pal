# Updates for Pal (Ashish Times) - project guide for Claude

Personal newspaper of Ashish Pal. Live at https://pal669.github.io/updates-for-pal/ (repo Pal669/updates-for-pal, public, branch main).
This repo is self-contained: it works from any machine with git and Python 3. Nothing depends on Ashish's Windows PC.

## Hard rules
- Python standard library only. No pip packages, no API keys, no AI calls, no CDN libraries. Plain HTML/CSS/JS.
- The site is public. Never add client names, portfolios, personal data, firm branding ("Neo Wealth") or secrets.
- Never delete files or data. Existing items in data/*.json are never dropped by hand.
- Do not change a desk you were not asked to touch. Ashish names new desks himself.
- Ashish's tone: casual, direct, no emojis. Explain a technical term with a plain-English version in brackets.

## Layout
- index.html, style.css, app.js: the whole front end. Desks are registered in app.js as DESKS.<name>.
- data/*.json: what each desk shows (items, listed, companies, company_notes, profiles, immigration_files, front, ...).
- scripts/*.py: collectors that write data/*.json (fetch_policies, fetch_startups, fetch_immigration, fetch_listed,
  company_intel, build_front_page, brief, enrich).
- .github/workflows/update.yml: GitHub Actions runs every collector several times a day and commits the data. This is what
  keeps the paper fresh, so the Mac or PC does NOT need to be on.
- README.md: full description of every desk and how to tune it.

## Working on it (any machine)
1. First: `git pull --rebase`. The GitHub bot commits data several times a day, and another machine may have pushed.
   Skipping this is how edits get overwritten or pushes get rejected.
2. Edit. Preview: `python3 -m http.server 8000` then open http://localhost:8000
3. Front-end change (app.js or style.css): bump the `?v=` number on both links in index.html, or browsers show the old
   version from cache.
4. `node --check app.js` if node exists (catches syntax errors before they break the live page).
5. Commit, `git pull --rebase`, `git push`. Pages updates in 1-2 minutes. Pushing publishes to the public site, so confirm
   with Ashish before pushing unless he already said to.
6. To refresh data by hand: `python3 scripts/fetch_listed.py` etc., or run the "update" workflow from the GitHub Actions tab.

## Current features worth knowing
- Investment Advisory Universe desk: see README. No commentary, ever (Ashish's rule): figures, headlines, links. PMS/AIF cards
  must show source and "as of". Monthly by-hand steps: `python scripts/apmi_aum.py` and `python scripts/aif_cat3.py` (need pypdf).
- Listed Universe desk: every company name (card top row and the "About <company>" line) links to
  https://www.screener.in/company/<NSE symbol or BSE code>/ via the scr() helper in app.js. Keep that when editing card().
- Front Page ranks stories by transparent points (scripts/build_front_page.py).
- Country Files and Startup Files are hand-written, dated facts; re-verify before relying on them.
