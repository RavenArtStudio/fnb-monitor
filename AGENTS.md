# Working on fnb-monitor

Daily monitoring of fnbperformance.com. Read README.md first.

- `snapshot/snapshot.py` builds every card; `snapshot/cube.py` scores the search visibility cube.
- `data/cube.json` holds blocks, sub-metrics, weights, Nov 13 audit scores and stage targets. A sub-metric with `"auto": null` keeps its audit score; to update one by hand, change its `audit` value and note the date in `evidence`.
- `data/targets.json` holds the 17 target searches; `data/semrush.json` the Semrush readings (refreshed by hand).
- `tools/build_html.py tools/board-replica.html data/cards.json "FNB Performance cards.html" "Checkpoint N"` rebuilds the desktop file. After every rebuild, copy it to `index.html` too: GitHub Pages serves `index.html` from main at https://ravenartstudio.github.io/fnb-monitor/. Keep the board look unchanged (Charcoal tokens, regular-weight type, no bold except where the engine already uses it).
- Paper edition: add `paper` as a fifth argument to build `paper.html` (same layout; `tools/theme-paper.css` on top, Bodoni Moda from `tools/fonts`, SIL Open Font License). Rebuild it whenever the board changes so both editions stay in step.
- Never commit keys. Google access comes only from the GOOGLE_SA_KEY Actions secret.
- Card copy: plain, short, professional; no marketing words.
