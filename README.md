# fnb-monitor

Daily monitoring snapshots for fnbperformance.com.

- `.github/workflows/snapshot.yml` runs every 3 hours (at :41 past 00, 03, 06 … UTC) and on demand. Each day keeps one history entry; the last run of the day wins.
- `snapshot/snapshot.py` reads Google Analytics 4 (property 557948137), Search Console (sc-domain:fnbperformance.com), crawls the live site and reads `data/semrush.json`.
- Output: `data/cards.json` (what the desktop file draws, with every time window), `data/history/YYYY-MM-DD.json` (one line of readings per day) and `data/runs.json` (site-check readings of each run, 40 days).
- `.github/workflows/live.yml` runs every 15 minutes: `snapshot/live.py` reads Google Analytics Realtime and publishes `data/live.json` on the `live` branch for the 30m, 12h and 24h windows.
- `tools/build_html.py` builds `FNB Performance cards.html`, which shows the copy saved inside it and then loads the latest `data/cards.json` from this repo. The same page is served at https://ravenartstudio.github.io/fnb-monitor/ (GitHub Pages, from `index.html` on main).

Google access uses the service account `fnb-monitor-reader@fnb-monitor.iam.gserviceaccount.com` (Viewer in Analytics, Restricted in Search Console). Its key lives only in the `GOOGLE_SA_KEY` Actions secret.

This repo is public: every number in `data/` can be read by anyone with the link.
