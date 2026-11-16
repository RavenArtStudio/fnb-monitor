# fnb-monitor

Daily monitoring snapshots for fnbperformance.com.

- `.github/workflows/snapshot.yml` runs every day at 01:41 UTC (07:11 India) and on demand.
- `snapshot/snapshot.py` reads Google Analytics 4 (property 557948137), Search Console (sc-domain:fnbperformance.com), crawls the live site and reads `data/semrush.json`.
- Output: `data/cards.json` (what the desktop file draws) and `data/history/YYYY-MM-DD.json` (one line of readings per day).
- `tools/build_html.py` builds `FNB Performance cards.html`, which shows the copy saved inside it and then loads the latest `data/cards.json` from this repo.

Google access uses the service account `fnb-monitor-reader@fnb-monitor.iam.gserviceaccount.com` (Viewer in Analytics, Restricted in Search Console). Its key lives only in the `GOOGLE_SA_KEY` Actions secret.

This repo is public: every number in `data/` can be read by anyone with the link.
