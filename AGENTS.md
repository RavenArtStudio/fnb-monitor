# Working on fnb-monitor

Daily monitoring of fnbperformance.com. Read README.md first.

- `snapshot/snapshot.py` builds every card; `snapshot/cube.py` scores the search visibility cube.
- `data/cube.json` holds blocks, sub-metrics, weights, Nov 13 audit scores and stage targets. A sub-metric with `"auto": null` keeps its audit score; to update one by hand, change its `audit` value and note the date in `evidence`.
- `data/targets.json` holds the 17 target searches; `data/semrush.json` the Semrush readings (refreshed by hand).
- `tools/build_html.py tools/board-replica.html data/cards.json "FNB Performance cards.html" "Checkpoint N"` rebuilds the desktop file. After every rebuild, copy it to `index.html` too: GitHub Pages serves `index.html` from main at https://ravenartstudio.github.io/fnb-monitor/. Keep the board look unchanged (Charcoal tokens, regular-weight type, no bold except where the engine already uses it).
- Two looks in one board (Checkpoint 26): Charcoal and Paper. `tools/theme-paper.css` is scoped under `html.paper` at build time and Bodoni Moda is embedded from `tools/fonts` (SIL Open Font License). A switch in the top bar flips the look and remembers it; `?theme=paper` or `?theme=charcoal` picks one. `paper.html` only redirects to `./?theme=paper`.
- Never commit keys. Google access comes only from the GOOGLE_SA_KEY Actions secret.
- Card copy: plain, short, professional; no marketing words.
- Time windows (Checkpoint 27): one toggle in the top bar, `30m 12h 24h 7d 30d All` (keys 1 to 6, remembered per browser, `?w=30m` in the address picks one). Each window ends at its latest complete minute, hour or day and is compared with the window of the same length before it; All runs from the Nov 15 launch with no comparison. `snapshot/windows.py` holds the rules and the bundle builders.
  - A card's own fields stay the 7-day view. Other windows sit in `card.w[<window>]` with the same fields; `card.wins` lists the windows the card can serve. If the chosen window is not served, the board shows the nearest longer one and says so beside the subtitle. Semrush cards carry `fixed` (month by month only).
  - Analytics 30m, 12h and 24h come from `snapshot/live.py` (Google Analytics Realtime), run every 15 minutes by `.github/workflows/live.yml`. It keeps its own minute log and publishes `data/live.json` and `data/live-log.json` on the `live` branch as one overwritten commit (never merge that branch into main). Realtime has no sessions, engagement, source, entry page or host name: sessions are session_start events, new visitors first_visit; Engaged sessions has no live view. If the newest live reading is over 45 minutes old the board says the feed is paused.
  - Search Console 12h and 24h use Google's hourly data (`HOUR`, `HOURLY_ALL`, partial for the latest hours). Site checks: 12h and 24h use each run in `data/runs.json` (rolling 40 days); 30d and All use `data/history`. The cube: 30d is a strip of day cells, All one column per week.
  - Times inside card text are markers (`@@2026-11-18T20:15Z@@`, `@@d:...@@` with the date); the board shows them in the viewer's local time.
  - `tools/build_html.py` takes an optional sixth argument, a `live.json` to save in the file (fetch it from the `live` branch before building the desktop file).

- `.github/workflows/build.yml` ("Build board", run by hand) rebuilds `index.html` and the desktop file from `data/cards.json` plus the live feed; use it after changing `tools/` instead of committing the large HTML files. `.github/workflows/apply.yml` ("Apply patch") applies a `*.patch.gz` or `*.patch` uploaded to the repo root on github.com, commits and removes it (for sessions that can upload but not push; patches must not touch `.github/workflows`).
