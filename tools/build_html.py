"""Builds 'FNB Performance cards.html' from the board engine (replica of public/app.js r3.30).

Usage: python tools/build_html.py <replica.html> <cards.json for the saved copy> <out.html> <checkpoint label> [default theme] [live.json]
Checkpoint 27: a time window toggle in the top bar (30m 12h 24h 7d 30d All); see AGENTS.md.
Both looks are in every build (Checkpoint 26): Charcoal, and Paper from tools/theme-paper.css scoped under html.paper,
with Bodoni Moda embedded. A switch in the top bar flips between them and remembers the choice (localStorage);
?theme=paper or ?theme=charcoal in the address picks one. The optional fifth argument sets the default (charcoal).
The page draws the saved copy at once, then loads data/cards.json from GitHub and redraws if newer.

Layout (Checkpoint 9): card rail on the left; on the right a workspace for the selected card:
header, live strip, chart with next steps beside it, then up to three breakdowns.
The engine's chart, bars and Details dialog are reused unchanged.
"""
import base64
import json
import os
import re
import sys

rep, snap, out, cp = sys.argv[1:5]
theme = sys.argv[5] if len(sys.argv) > 5 else 'charcoal'
src = open(rep, encoding='utf-8').read().split('\n')
css = '\n'.join(src[4:574])
engine = '\n'.join(src[587:680])
for a, b in [('>Day by day${', ">${esc(d.main.heading||'Day by day')}${"),
             ("${esc(where)}, last ${d.period} days", "${esc(where)}, ${esc(d.periodLabel||('last '+d.period+' days'))}"),
             ("const fmt=(n)=>n===null||n===undefined?'--':Number(n).toLocaleString('en-US',{maximumFractionDigits:0});",
              "const fmt=(n)=>n===null||n===undefined?'--':Number.isInteger(Number(n))?Number(n).toLocaleString('en-US'):Number(n).toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:2});"),
             ("const top=niceTop(Math.max(1,...all)*1.08);", "const top=unit==='points'?10:niceTop(Math.max(1,...all)*1.08);"),
             # Checkpoint 27: time keys ('2026-11-18T20:15Z') for the short windows, and time markers in card text
             ("const nice=(iso)=>iso?new Date(", "const nice=(iso)=>iso&&iso.length>10?tipT(iso):iso?new Date("),
             ("const shortDate=(iso)=>iso?new Date(", "const shortDate=(iso)=>iso&&iso.length>10?tlab(iso,false):iso?new Date("),
             (r"""'"':'&quot;',"'":'&#39;'}[c]));}""",
              r"""'"':'&quot;',"'":'&#39;'}[c])).replace(/@@(d:)?(\d{4}-\d\d-\d\dT\d\d:\d\dZ)@@/g,(m,d,t)=>tlab(t,!!d));}"""),
             ('aria-label="Daily ${esc(unit)} by business, with gaps for days without data"',
              'aria-label="${esc(unit)} over time, with gaps where there is no reading"')]:
    assert engine.count(a) == 1, a
    engine = engine.replace(a, b)
saved = json.load(open(snap, encoding='utf-8'))
live_path = sys.argv[6] if len(sys.argv) > 6 else None
saved_live = json.load(open(live_path, encoding='utf-8')) if live_path and os.path.exists(live_path) else None

CSS = r'''
/* ===== Checkpoint 9 shell ===== */
html{zoom:.9}
body *{font-weight:400!important}
.ws-hero,.detail-value,.ask-stat strong{font-weight:250!important}
.stop-fnb-performance{stop-color:var(--u0)}
.app{position:relative;z-index:1;max-width:1840px;margin:0 auto;padding:18px 32px 12px;display:grid;grid-template-columns:292px minmax(0,1fr);gap:0 36px;align-items:start}
.topbar{grid-column:1/-1;display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;font-size:12.5px;color:var(--ink-3)}
.snap{display:inline-flex;align-items:center;gap:8px}
.snap i{width:6px;height:6px;border-radius:50%;background:var(--ink-4)}
.snap.live i{background:var(--good)}.snap.saved i{background:var(--warn)}
/* rail */
.rail{display:flex;flex-direction:column;min-width:0;position:sticky;top:16px}
.rail-group{display:flex;align-items:center;gap:10px;font-size:11.5px;color:var(--ink-4);margin:10px 0 3px;padding:0 10px}
.rail-group:first-child{margin-top:0}
.rail-group::after{content:"";flex:1;height:1px;background:var(--line-soft)}
.rail-group svg{width:13px;height:13px;flex:none;fill:none;stroke:var(--ink-3);stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round;margin-right:-3px}
.rail-item{appearance:none;border:0;background:transparent;display:grid;grid-template-columns:minmax(0,1fr) auto 48px;gap:10px;align-items:baseline;text-align:left;padding:5px 10px;border-radius:10px;font-size:13.5px;color:var(--ink-2);transition:background .2s var(--ease),color .2s}
.rail-item:hover{background:var(--surface);color:var(--ink)}
.rail-item[aria-selected="true"]{background:var(--surface-2);color:var(--ink)}
*{scrollbar-width:none!important;-ms-overflow-style:none!important}*::-webkit-scrollbar{display:none!important;width:0!important;height:0!important}
.heat-key>span{white-space:nowrap}
.r1.hm{grid-template-columns:minmax(0,1.7fr) minmax(0,1fr)}.r1.hm>.np{max-height:none;position:relative}.r1.hm>.np>div{position:absolute;inset:18px 20px 16px;overflow:auto}.r1.hm .steps{display:flex;flex-direction:column;gap:2px}
.r3{display:grid;grid-template-columns:repeat(var(--k),minmax(0,1fr));gap:14px}
.col-trend{fill:none;stroke:var(--ink-3,#9a9a9a);stroke-width:1.6;stroke-dasharray:1.5 4.5;stroke-linecap:round;stroke-linejoin:round;pointer-events:none}.col-dot{fill:var(--ink-3,#9a9a9a);pointer-events:none}
.rail-item span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rail-item strong{font-variant-numeric:tabular-nums;color:var(--ink)}
.rail-item em{font-style:normal;font-size:12px;text-align:right;font-variant-numeric:tabular-nums;color:var(--ink-4)}
.rail-item em.up{color:var(--good)}.rail-item em.down{color:var(--bad)}
/* workspace */
.ws{min-width:0;display:flex;flex-direction:column;gap:14px;animation:wsIn .45s var(--ease)}
@keyframes wsIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.ws-top{display:flex;justify-content:space-between;align-items:center;gap:24px;padding:4px 4px 2px}
.wt-l h2{font-size:24px;letter-spacing:-.02em;color:var(--ink)}
.wt-l p{font-size:13px;color:var(--ink-3);margin-top:4px}
.wt-r{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;justify-content:flex-end}
.wt-r .ws-hero{font-size:44px}
.wt-r .all{margin-left:10px}
.slim{display:grid;grid-template-columns:repeat(var(--k),minmax(0,1fr));background:var(--surface);border-radius:var(--r-md);box-shadow:0 0 0 1px #ffffff09 inset}
.slim>div{padding:10px 18px;display:flex;align-items:baseline;gap:10px;min-width:0}
.slim>div+div{border-left:1px solid var(--line-soft)}
.slim span{font-size:12px;color:var(--ink-3);white-space:nowrap}
.slim b{font-size:16px;color:var(--ink);font-variant-numeric:tabular-nums;white-space:nowrap}
.slim small{font-size:11.5px;color:var(--ink-4);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.slim small.down{color:var(--bad)}.slim small.up{color:var(--good)}
.ws-head{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;padding:2px 4px 0}
.ws-head h2{font-size:24px;letter-spacing:-.02em;color:var(--ink)}
.ws-head p{font-size:13px;color:var(--ink-3);margin-top:4px}
.strip{display:grid;grid-template-columns:minmax(260px,1.35fr) repeat(var(--k),minmax(0,1fr));background:var(--surface);border-radius:var(--r-lg);box-shadow:0 0 0 1px #ffffff09 inset,0 30px 60px -40px #000c}
.strip>div{padding:18px 22px;min-width:0}
.strip>div+div{border-left:1px solid var(--line-soft)}
.ws-hero{font-family:var(--display);font-size:50px;letter-spacing:-.045em;line-height:1;color:var(--ink);font-variant-numeric:tabular-nums}
.ws-hero small{font-size:15px;letter-spacing:0;color:var(--ink-3);margin-left:8px}
.hero-line{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.chip{font-size:12.5px;padding:4px 11px;border-radius:999px;background:var(--surface-2);color:var(--ink-2);white-space:nowrap}
.chip.up{color:var(--good)}.chip.down{color:var(--bad)}
.hero-cap{font-size:12.5px;color:var(--ink-3);margin-top:10px}
.kpi .k-l{font-size:12px;color:var(--ink-3)}
.kpi .k-v{font-family:var(--display);font-size:22px;letter-spacing:-.02em;color:var(--ink);margin-top:6px;font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kpi .k-n{font-size:12px;color:var(--ink-3);margin-top:4px}
.kpi .k-n.up{color:var(--good)}.kpi .k-n.down{color:var(--bad)}
.r1{display:grid;grid-template-columns:minmax(0,2fr) repeat(var(--k),minmax(0,1fr));gap:14px;align-items:stretch}
.r1>section:first-child{display:flex;flex-direction:column}
.r1.tight>section:first-child{padding:16px 18px 14px}.r1.tight .ph{margin-bottom:8px}
.r2{display:grid;grid-template-columns:1fr;gap:14px;align-items:stretch}
.r2.has3{grid-template-columns:minmax(0,2fr) minmax(0,1fr)}
.bdp .hbar{grid-template-columns:minmax(80px,46%) 1fr 3.2em;font-size:12.5px}
.bdp .hbar span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bdp .hbars{gap:10px}
.r2 .np{max-height:none;overflow:visible}
.r2 .steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:4px 22px}
.r2 .st{border-top:0;padding:2px 0 6px;border-left:0}
.ws-main{display:grid;grid-template-columns:minmax(0,1.9fr) minmax(300px,1fr);gap:16px;align-items:start}
.ws .panel{padding:20px 22px}
.ph{font-size:12.5px;color:var(--ink-3);margin:0 0 14px;display:flex;justify-content:space-between;gap:12px}
.ph span{color:var(--ink-4)}.ph .more{font:inherit;color:var(--ink-3);background:none;border:0;padding:0;cursor:pointer}.ph .more:hover{color:var(--ink-1)}
.ws-main>section{display:flex;flex-direction:column}
.ws-main.tight{align-items:start}
.ws-main.tight>section{padding:16px 18px 14px}
.ws-main.tight .ph{margin-bottom:8px}
.ws-main.tight .np{max-height:392px}
.ws-chart{flex:none;height:clamp(210px,17vw,290px)}
.demo-note:empty{display:none}
.np{display:flex;flex-direction:column;gap:18px;max-height:calc(clamp(210px,17vw,290px) + 74px);overflow:auto;scrollbar-width:none}
.steps{list-style:none;margin:0;padding:0;display:flex;flex-direction:column}
.st{display:grid;grid-template-columns:10px minmax(0,1fr);gap:12px;padding:11px 0;border-top:1px solid var(--line-soft)}
.st:first-child{border-top:0;padding-top:2px}
.sd{width:7px;height:7px;border-radius:50%;margin-top:7px;background:var(--ink-4)}
.sd.high{background:var(--u3)}.sd.med{background:var(--u1)}
.st-t{font-size:13.5px;color:var(--ink);line-height:1.5}
.st-w{font-size:12.5px;color:var(--ink-3);margin-top:3px;line-height:1.5}
.st-o{display:inline-flex;gap:10px;font-size:11.5px;color:var(--ink-4);margin-top:5px}
.st-o b{color:var(--good)}
.so{display:flex;flex-direction:column;gap:10px}
.so-i{font-size:12.5px;color:var(--ink-3);line-height:1.5;padding-left:14px;position:relative}
.so-i::before{content:"";position:absolute;left:0;top:7px;width:6px;height:6px;border-radius:50%;background:var(--ink-4)}
.so-i.caution::before{background:var(--warn)}.so-i.gap::before{background:var(--u2)}.so-i.concentration::before{background:var(--u1)}.so-i.peak::before{background:var(--good)}
.so-i span{display:block;color:var(--ink-2);font-size:13px}
.bds{display:grid;grid-template-columns:repeat(var(--b),minmax(0,1fr));gap:16px}
.bds .hbar{grid-template-columns:minmax(90px,44%) 1fr 3.4em;font-size:12.5px}
.bds .hbar span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bds .hbars{gap:11px}
.empty-note{font-size:12.5px;color:var(--ink-4)}
.link-quiet.all{font-size:12.5px}
/* columns chart */
.col-cur{fill:var(--u0);opacity:.62;transition:opacity .2s}
.col-cur:hover{opacity:.9}
.col-prev{stroke:var(--ink-4);stroke-width:1.5;stroke-dasharray:3 3}
.col-val{fill:var(--ink-2);font-size:11.5px}
.launch line{stroke:var(--u1);stroke-width:1;stroke-dasharray:2 4;opacity:.8}
.launch text{fill:var(--u1);font-size:11px}
.early rect{fill:var(--ink-4);opacity:.1}
/* page speed: page list beside the chart, file types in a popup */
.r1.sp{grid-template-columns:minmax(0,1fr) minmax(0,1.05fr)}
.pgp{display:flex;flex-direction:column;padding-bottom:10px}
.pgl{position:relative;flex:1;min-height:0;margin:0 -8px}
.pgl>div{position:absolute;inset:0;overflow:auto}
.pgr,.pgh{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(50px,1fr) 4.4em 4.6em 5.6em;gap:12px;align-items:center;padding:6px 8px;text-align:left}
.pgh{position:sticky;top:0;z-index:1;background:var(--surface);font-size:11.5px;color:var(--ink-4);padding-top:0}
.pgh span:nth-child(n+3){text-align:right}
.pgr{appearance:none;border:0;background:transparent;width:100%;border-radius:8px;font-size:12.5px;color:var(--ink-2);cursor:pointer;transition:background .2s var(--ease),color .2s}
.pgr:hover,.pgr:focus-visible{background:var(--surface-2);color:var(--ink);outline:0}
.pgn{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pgb{height:5px;border-radius:99px;background:var(--surface-3);overflow:hidden}
.pgb i{display:block;height:100%;border-radius:99px;background:var(--u0);opacity:.55}
.pgr b,.pgr em{text-align:right;font-style:normal;font-variant-numeric:tabular-nums}
.pgr b{color:var(--ink)}.pgr b.warn{color:var(--warn)}.pgr b.bad{color:var(--bad)}
.pgr em{color:var(--ink-3)}
.pgr small{font-size:11.5px;color:var(--ink-4);text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.detail.sheet.pg{width:min(560px,calc(100vw - 48px))}
.ftl{display:flex;flex-direction:column}
.ftr{display:grid;grid-template-columns:6.5em minmax(0,1fr) 4em 3em;gap:12px;align-items:center;padding:6px 0;font-size:12.5px;color:var(--ink-3);border-top:1px solid var(--line-soft)}
.ftr:first-child{border-top:0;padding-top:2px}
.ftr .tr{height:6px;border-radius:99px;background:var(--surface-3);overflow:hidden}
.ftr .fl{display:block;height:100%;border-radius:99px;background:var(--ink-4)}
.ftr b,.ftr em{text-align:right;font-style:normal;font-variant-numeric:tabular-nums;color:var(--ink-2)}
.ftr em{color:var(--ink-4)}
.ftr.top{color:var(--ink)}.ftr.top .fl{background:var(--u0)}.ftr.top b{color:var(--ink)}
.lr small{color:var(--ink-4);margin-left:6px}
a.pbtn{text-decoration:none;display:inline-flex;align-items:center}
.early text{fill:var(--ink-3);font-size:11px}
/* heatmap */
.heat{display:flex;flex-direction:column;gap:2px}
.heat-row{appearance:none;border:0;background:transparent;display:grid;align-items:center;gap:6px;padding:0 8px;height:29px;border-radius:8px;text-align:left;color:var(--ink-2);font-size:13px;width:100%;transition:background .2s var(--ease)}
button.heat-row:hover{background:var(--surface-2);color:var(--ink)}
.heat-row.head{font-size:11.5px;color:var(--ink-4);height:20px}
.heat-row .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:flex;align-items:center;gap:8px}
.heat-row .nm small{color:var(--ink-4);font-size:11.5px}
.heat-row .tg{text-align:right;font-variant-numeric:tabular-nums;color:var(--ink-3);font-size:12.5px}
.heat-row.head span{text-align:center}.heat-row.head span:first-child{text-align:left}.heat-row.head span:last-child{text-align:right}
.cell{height:22px;border-radius:6px;display:grid;place-items:center;font-size:12.5px;font-variant-numeric:tabular-nums;color:var(--ink)}
.cell.good{background:color-mix(in srgb,var(--good) 30%,var(--surface))}.cell.warn{background:color-mix(in srgb,var(--warn) 26%,var(--surface))}.cell.bad{background:color-mix(in srgb,var(--bad) 28%,var(--surface))}
.cell.now.good{background:color-mix(in srgb,var(--good) 58%,var(--surface));color:#1d1e20}.cell.now.warn{background:color-mix(in srgb,var(--warn) 52%,var(--surface));color:#1d1e20}.cell.now.bad{background:color-mix(in srgb,var(--bad) 58%,var(--surface));color:#1d1e20}
.cell.none{background:var(--surface-2);color:var(--ink-4)}
/* heatmap, Checkpoint 24: 7 days in view, earlier days scroll left behind pinned names, audit and target */
.hscroll{overflow-x:auto;overflow-y:hidden;overscroll-behavior-x:contain}
.hscroll.drag{cursor:grabbing;user-select:none}
.hgrid{position:relative;display:flex;flex-direction:column;gap:2px;width:max-content;min-width:100%}
.hgrid .heat-row{--hb:var(--surface);grid-template-columns:calc(var(--nw) + 6px + var(--cw)) repeat(var(--n),var(--cw)) 52px;column-gap:6px;padding:0}
.hgrid button.heat-row:hover{--hb:var(--surface-2)}
.hgrid .lead{position:sticky;left:0;z-index:2;align-self:stretch;display:grid;grid-template-columns:minmax(0,1fr) var(--cw);gap:6px;align-items:center;padding-left:8px;background:var(--hb);border-radius:8px 0 0 8px;box-shadow:6px 0 0 var(--hb),-3px 0 0 var(--surface);transition:background .2s var(--ease),box-shadow .2s var(--ease)}
.hgrid .tg{position:sticky;right:0;z-index:2;align-self:stretch;display:flex;align-items:center;justify-content:flex-end;padding-right:8px;background:var(--hb);border-radius:0 8px 8px 0;box-shadow:-6px 0 0 var(--hb),3px 0 0 var(--surface);transition:background .2s var(--ease),box-shadow .2s var(--ease)}
.hgrid .lead::after,.hgrid .tg::before{content:"";position:absolute;top:0;bottom:0;width:26px;pointer-events:none;opacity:0;transition:opacity .3s var(--ease)}
.hgrid .lead::after{right:-32px;background:linear-gradient(90deg,var(--hb),transparent)}
.hgrid .tg::before{left:-32px;background:linear-gradient(270deg,var(--hb),transparent)}
.heat.more-l .hgrid .lead::after,.heat.more-r .hgrid .tg::before{opacity:1}
.hgrid .heat-row.stage .lead::after,.hgrid .heat-row.stage .tg::before{display:none}
.hgrid .heat-row.head .lead span:first-child{text-align:left}.hgrid .heat-row.head .hc{text-align:center}.hgrid .heat-row.head .tg{text-align:right}
.hgrid .hc.fut{opacity:.55}
.hgrid .heat-row.head .tg,.hgrid .heat-row.stage .tg{font-size:11.5px;color:var(--ink-4)}
.hgrid .stg .sl{position:sticky;left:calc(var(--nw) + 13px + var(--cw));z-index:1;background:var(--surface);padding-right:6px;margin-right:-6px}
.r1.hm>.np>div.fade-b{-webkit-mask-image:linear-gradient(180deg,#000 calc(100% - 44px),transparent);mask-image:linear-gradient(180deg,#000 calc(100% - 44px),transparent)}
.hgrid .heat-row.stage{height:16px;font-size:11px;color:var(--ink-4)}
.hgrid .stg{display:flex;align-items:center;gap:8px;min-width:0;white-space:nowrap;overflow:clip;padding-left:1px}
.hgrid .stg::after{content:"";flex:1;height:1px;background:var(--line-soft)}
.hgrid .stg.cur{color:var(--ink-3)}
.hgrid .sline{position:absolute;top:2px;bottom:0;width:1px;background:var(--line);pointer-events:none;z-index:1}
.cell.slot{background:transparent;box-shadow:0 0 0 1px var(--line-soft) inset}
.heat-key .hint{color:var(--ink-3)}
/* look switch, Checkpoint 26 */
.tb-r{display:flex;align-items:center;gap:16px}
.theme-tg{display:inline-flex;gap:2px;padding:2px;border-radius:999px;box-shadow:0 0 0 1px var(--line) inset}
.theme-tg button{appearance:none;border:0;background:transparent;color:var(--ink-3);font:inherit;font-size:12px;line-height:1;padding:5px 11px 5px 8px;border-radius:999px;cursor:pointer;display:inline-flex;align-items:center;gap:7px;transition:background .25s var(--ease),color .25s}
.theme-tg button:hover{color:var(--ink)}
.theme-tg button i{width:9px;height:9px;border-radius:50%;box-shadow:0 0 0 1px #8a8984 inset}
.theme-tg button[data-theme="charcoal"] i{background:#27282b}.theme-tg button[data-theme="paper"] i{background:#e8e3d8}
.theme-tg button[aria-pressed="true"]{background:var(--surface-2);color:var(--ink)}
html.paper .theme-tg button[aria-pressed="true"]{background:var(--black);color:var(--onblack)}
/* time window toggle, Checkpoint 27 */
.topbar{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);gap:16px}
.topbar .tb-r{justify-self:end}
.snap{gap:18px}.sn{display:inline-flex;align-items:center;gap:8px;white-space:nowrap}
.sn i{width:6px;height:6px;border-radius:50%;background:var(--ink-4)}.sn.live i{background:var(--good)}.sn.saved i{background:var(--warn)}
.win-tg{display:inline-flex;gap:2px;padding:2px;border-radius:999px;box-shadow:0 0 0 1px var(--line) inset;transition:opacity .25s var(--ease)}
.win-tg button{appearance:none;border:0;background:transparent;color:var(--ink-3);font:inherit;font-size:12px;line-height:1;min-width:40px;padding:5px 11px;border-radius:999px;cursor:pointer;position:relative;font-variant-numeric:tabular-nums;transition:background .25s var(--ease),color .25s,box-shadow .25s}
.win-tg button:hover{color:var(--ink)}
.win-tg button[aria-pressed="true"]{background:var(--surface-2);color:var(--ink)}
.win-tg button.na{color:var(--ink-4)}
.win-tg button.na[aria-pressed="true"]{background:transparent;color:var(--ink-3);box-shadow:0 0 0 1px var(--line) inset}
.win-tg button.shown::after{content:"";position:absolute;left:50%;bottom:2px;width:3px;height:3px;margin-left:-1.5px;border-radius:50%;background:var(--ink-3)}
.win-tg.off{opacity:.55}
html.paper .win-tg button[aria-pressed="true"]{background:var(--black);color:var(--onblack)}
html.paper .win-tg button.na[aria-pressed="true"]{background:transparent;color:var(--ink-2);box-shadow:0 0 0 1px var(--ink-3) inset}
.ws-top .wt-l{min-width:0;flex:1}
.wt-l p{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.wt-l .wn{margin-left:10px;padding-left:10px;border-left:1px solid var(--line);color:var(--ink-2)}
.wt-l .wn.warn{color:var(--warn)}
.rail-item.fb strong,.rail-item.fb em{opacity:.42}
.col-gap{fill:none;stroke:var(--ink-4);stroke-dasharray:2 3;stroke-width:1}
.col-part{opacity:.5}
.col-prev{fill:none;stroke:var(--ink-3);stroke-width:1;stroke-dasharray:2 2.5;opacity:.75}
.hgrid.dense .heat-row.head .hc{padding-left:4px}
@media (max-width:1100px){.topbar{grid-template-columns:minmax(0,1fr) auto;row-gap:10px}.topbar .win-tg{grid-row:2;grid-column:1/-1;justify-self:start}.snap{flex-wrap:wrap;row-gap:4px}}
.col-empty{fill:var(--ink-4);font-size:13px}
.hgrid .heat-row{grid-template-columns:calc(var(--nw) + 6px + var(--aw,var(--cw))) repeat(var(--n),var(--cw)) 52px;column-gap:var(--gp,6px)}
.hgrid .lead{grid-template-columns:minmax(0,1fr) var(--aw,var(--cw))}
.hgrid .stg .sl{left:calc(var(--nw) + 13px + var(--aw,var(--cw)))}
.hgrid.dense .heat-row.head .hc{overflow:visible;white-space:nowrap;text-align:left}
.hgrid.dense .heat-row.head .lead .hc{text-align:center}
@media (max-width:1100px){.r1.hm{grid-template-columns:minmax(0,1fr)}.r1.hm>.np>div{position:static}.heat-key{flex-wrap:wrap;row-gap:4px}}
/* popups (compact, sectioned) */
.detail.sheet{width:min(820px,calc(100vw - 48px));height:fit-content;max-height:min(860px,calc(100vh - 48px))}
.detail.sheet .detail-inner{overflow:auto;scrollbar-width:none}
.pp-head{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:12px 14px 12px 22px;border-bottom:1px solid var(--line-soft);position:sticky;top:0;background:var(--canvas);z-index:2}
.ph-t{display:flex;align-items:center;gap:12px;flex-wrap:wrap;min-width:0}
.pp-head .detail-title{font-size:19px;letter-spacing:-.015em}
.ph-k{font-size:12px;color:var(--ink-4)}
.pp-head .detail-close{width:34px;height:34px}
.pp{padding:12px 22px 18px;display:flex;flex-direction:column;gap:10px}
.pill{display:inline-block;font-size:12px;padding:3px 10px;border-radius:999px;background:var(--surface-2);color:var(--ink-2)}
.pill.good{background:color-mix(in srgb,var(--good) 16%,var(--surface));color:var(--good)}
.pill.warn{background:color-mix(in srgb,var(--warn) 16%,var(--surface));color:var(--warn)}
.pill.bad{background:color-mix(in srgb,var(--bad) 16%,var(--surface));color:var(--bad)}
.box{background:var(--surface);border-radius:12px;padding:11px 14px;box-shadow:0 0 0 1px var(--line-soft) inset}
.box h4{font-size:13px;color:var(--ink);margin:0 0 7px;display:flex;justify-content:space-between;gap:12px}
.box h4 span{font-size:12px;color:var(--ink-4)}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px 18px}
.kv span{display:block;font-size:12px;color:var(--ink-3)}
.kv b{display:block;font-size:14px;color:var(--ink);margin-top:3px;font-variant-numeric:tabular-nums;overflow:hidden;text-overflow:ellipsis}
.kv b.up{color:var(--good)}.kv b.down{color:var(--bad)}
.kv small{display:block;font-size:11.5px;color:var(--ink-4);margin-top:2px}
.sml{display:flex;flex-direction:column}
.smr{display:grid;grid-template-columns:minmax(0,1fr) 200px 40px;gap:2px 14px;align-items:center;padding:8px 0;border-top:1px solid var(--line-soft)}
.smr:first-child{border-top:0;padding-top:2px}
.smn{font-size:13px;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.smn em{font-style:normal;font-size:11px;color:var(--ink-4);margin-left:8px}
.smw{text-align:right;font-size:11.5px;color:var(--ink-4)}
.sme{grid-column:1/-1;font-size:12px;color:var(--ink-3);line-height:1.45}
.sbar{display:grid;grid-template-columns:1fr 3em;gap:10px;align-items:center}
.sbar .tr{height:6px;border-radius:99px;background:var(--surface-3);overflow:hidden}
.sbar .fl{height:100%;border-radius:99px}
.fl.good{background:var(--good)}.fl.warn{background:var(--warn)}.fl.bad{background:var(--bad)}
.sbar b{text-align:right;color:var(--ink-2);font-variant-numeric:tabular-nums;font-size:12.5px}
.acts{list-style:none;margin:0;padding:0;display:flex;flex-direction:column}
.acts li{display:grid;grid-template-columns:10px minmax(0,1fr) auto;gap:10px;align-items:baseline;padding:7px 0;border-top:1px solid var(--line-soft);font-size:13px;color:var(--ink-2);line-height:1.5}
.acts li:first-child{border-top:0;padding-top:0}
.acts .sd{margin-top:0;transform:translateY(-1px)}
.ao{font-size:11.5px;color:var(--ink-4);white-space:nowrap}.ao b{color:var(--good)}
.pl{display:flex;flex-direction:column;gap:8px}
.pl>div{display:grid;grid-template-columns:10px minmax(0,1fr);gap:10px;align-items:baseline}
.pd{width:6px;height:6px;border-radius:50%;background:var(--ink-4);transform:translateY(-2px)}
.pd.caution{background:var(--warn)}.pd.gap{background:var(--u2)}.pd.concentration{background:var(--u1)}.pd.peak{background:var(--good)}.pd.movement{background:var(--ink-3)}
.pl b{font-size:13px;color:var(--ink)}.pl small{display:block;font-size:12px;color:var(--ink-3);margin-top:1px;line-height:1.45}
.bdg{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px 24px}
.bdg h5{font-size:12px;color:var(--ink-3);margin:0 0 6px}
.lr{display:flex;justify-content:space-between;gap:12px;font-size:12.5px;color:var(--ink-2);padding:3px 0}
.lr span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.lr b{color:var(--ink);font-variant-numeric:tabular-nums}
.pnote{font-size:12px;color:var(--ink-3);margin-top:10px;line-height:1.5}
.cav{margin:6px 0 0;padding-left:16px;font-size:12px;color:var(--ink-4);line-height:1.5}
.pbtns{display:flex;gap:10px;flex-wrap:wrap}
.pbtn{appearance:none;border:0;border-radius:12px;padding:9px 16px;font-size:13px;background:transparent;color:var(--ink);box-shadow:0 0 0 1px var(--line) inset;transition:background .2s,transform .3s var(--spring)}
.pbtn:hover{background:var(--surface-2)}.pbtn:active{transform:scale(.97)}
.pbtn.primary{background:var(--ink);color:#1d1e20;box-shadow:none}.pbtn.primary:hover{background:#fff}
.disc summary{cursor:pointer;font-size:12.5px;color:var(--ink-3);list-style:none;display:flex;align-items:center;gap:8px}
.disc summary::before{content:"›";display:inline-block;transition:transform .25s var(--ease)}
.disc[open] summary::before{transform:rotate(90deg)}
.disc .mini-wrap{margin-top:10px;max-height:260px;overflow:auto}
.heat-key{display:flex;gap:16px;align-items:center;font-size:11.5px;color:var(--ink-4);padding:8px 8px 0}
.heat-key i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.heat-key .good{background:color-mix(in srgb,var(--good) 58%,var(--surface))}.heat-key .warn{background:color-mix(in srgb,var(--warn) 52%,var(--surface))}.heat-key .bad{background:color-mix(in srgb,var(--bad) 58%,var(--surface))}
@media (max-width:1100px){.app{grid-template-columns:1fr;padding:16px}.rail{position:static;flex-direction:row;overflow-x:auto;gap:6px;padding-bottom:8px;scrollbar-width:none}.rail-group{display:none}.rail-item{display:flex;flex:none;gap:8px;white-space:nowrap;background:var(--surface);border-radius:999px;padding:9px 14px}.rail-item span{overflow:visible}.rail-item em{display:none}.ws-main{grid-template-columns:1fr}.strip{grid-template-columns:1fr 1fr}.strip>div+div{border-left:0}.bds{grid-template-columns:1fr}}
'''

JS = r'''
const SNAP_URL='https://raw.githubusercontent.com/RavenArtStudio/fnb-monitor/main/data/cards.json';
const SAVED=%s;
const SAVED_LIVE=%s;
let CARDS=[],ORDER=[],BY={},META={},cur=null;
const when=(iso)=>{const d=new Date(iso);return d.toLocaleDateString('en-US',{month:'short',day:'numeric'})+', '+d.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});};
const OWNER={site:'Site',owner:'Owner',google:'Google'};
const GROUP_ICON={
 'Overview':'<rect x="2" y="2" width="5" height="5" rx="1.2"/><rect x="9" y="2" width="5" height="5" rx="1.2"/><rect x="2" y="9" width="5" height="5" rx="1.2"/><rect x="9" y="9" width="5" height="5" rx="1.2"/>',
 'Enquiries':'<path d="M2.5 4.5a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v4.5a2 2 0 0 1-2 2H7l-3 2.5v-2.5h0a2 2 0 0 1-1.5-2z"/>',
 'Website':'<rect x="1.8" y="2.8" width="12.4" height="10.4" rx="2"/><path d="M1.8 6h12.4"/><path d="M4 4.4h.01M5.6 4.4h.01"/>',
 'Google Search':'<circle cx="7" cy="7" r="4.3"/><path d="m10.2 10.2 3.6 3.6"/>',
 'Site health':'<path d="M1.5 8.5h2.8l1.6-4 2.4 7.5 1.8-5 1 1.5h3.4"/>',
 'Authority':'<path d="M6.6 9.4a2.8 2.8 0 0 0 4 0l2.2-2.2a2.8 2.8 0 0 0-4-4l-.9.9"/><path d="M9.4 6.6a2.8 2.8 0 0 0-4 0L3.2 8.8a2.8 2.8 0 0 0 4 4l.9-.9"/>'};
function deltaOf(d){const s=d.stats;if(s.railText!==undefined)return {t:s.railText,c:s.railTone||''};if(d.level){const x=s.total-s.previousTotal;return {t:x===0?'level':(x>0?'+':'−')+fmt(Math.abs(x)),c:x>0?'up':x<0?'down':''};}
 if(s.change===null||s.change===undefined)return {t:'',c:''};return {t:s.change===0?'level':(s.change>0?'+':'−')+Math.abs(s.change)+'%%',c:s.change>0?'up':s.change<0?'down':''};}
function drawRail(){let g='',h='';for(const d0 of CARDS){const d=view(d0);if(d.group!==g){g=d.group;h+=`<div class="rail-group">${GROUP_ICON[g]?`<svg viewBox="0 0 16 16" aria-hidden="true">${GROUP_ICON[g]}</svg>`:''}${esc(g)}</div>`;}const x=deltaOf(d),fb=!d.fixed&&d._win!==WIN;
 h+=`<button class="rail-item${fb?' fb':''}" role="tab" id="tab-${d.id}" data-card="${d.id}" aria-selected="${d.id===cur}" tabindex="${d.id===cur?0:-1}"${fb?` title="${esc(WNAME[d._win]||'')}, ${esc(WLAB[WIN])} is not measured for this card"`:''}><span>${esc(d.short)}</span><strong>${fmt(d.stats.total)}</strong><em class="${x.c}">${esc(x.t)}</em></button>`;}
 el('rail').innerHTML=h;}

/* ---- live strip ---- */
const sd=(iso)=>shortDate(iso);
function kpisOf(d){if(d.kpis)return d.kpis;const s=d.stats,ser=Object.values(d.main.series)[0]||[],vals=ser.map(p=>p?.value),prev=(d.main.previous||[]).map(p=>p?.value);
 if(d.kind==='heatmap')return [];
 if(d.level){const have=ser.filter(p=>p&&p.value!=null);const out=[];
  if(prev.length&&prev.some(v=>v!=null)){out.push({label:d.main.tipLabel||'A week earlier',value:fmt(s.previousTotal)});}
  else if(have.length>1){out.push({label:'Previous reading',value:fmt(have.at(-2).value),note:sd(have.at(-2).date)});}
  else out.push({label:'Previous reading',value:'--',note:'First reading'});
  if(have.length){const mx=have.reduce((a,b)=>b.value>a.value?b:a),mn=have.reduce((a,b)=>b.value<a.value?b:a);out.push({label:'Highest',value:fmt(mx.value),note:sd(mx.date)});out.push({label:'Lowest',value:fmt(mn.value),note:sd(mn.date)});}
  return out;}
 const best=vals.reduce((bi,v,i)=>v>(vals[bi]??-1)?i:bi,0);
 const pt=prev.reduce((a,v)=>a+(v||0),0);
 return [d.main.previous?{label:d.main.tipLabel||'Previous period',value:fmt(s.previousTotal??pt)}:{label:'Counting from',value:sd(d.main.dates[0])},
  {label:s.avgLabel||'Daily average',value:fmt(s.avgPerDay),note:prev.length?`previous ${fmt(Math.round(pt/(prev.length||1)*10)/10)}`:''},
  vals[best]?{label:s.bestLabel||'Best day',value:fmt(vals[best]),note:ser[best]?sd(ser[best].date):''}:{label:s.bestLabel||'Best day',value:'--',note:'None yet'}];}
function chipOf(d){const s=d.stats;if(s.deltaText)return {t:s.deltaText,c:s.deltaTone||''};if(s.change!=null)return {t:`${s.change>0?'+':s.change<0?'\u2212':''}${Math.abs(s.change)}%% on the previous ${d.period} days`,c:s.change>0?'up':s.change<0?'down':''};return {t:'',c:''};}
function headHTML(d){const s=d.stats,ch=chipOf(d),unit=d.kind==='heatmap'?'of 10':esc(d.unit);
 const wn=wnote(d);
 return `<header class="ws-top"><div class="wt-l"><h2>${esc(d.label)}</h2><p>${esc(d.sub||d.source)}${wn?`<span class="wn ${wn.c}" title="${esc(wn.t)}">${esc(wn.t)}</span>`:''}</p></div><div class="wt-r"><span class="ws-hero">${fmt(s.total)}<small>${unit}</small></span>${ch.t?`<span class="chip ${ch.c}">${esc(ch.t)}</span>`:''}<button class="link-quiet all" data-detail="card">All details</button></div></header>`;}
function slimStrip(d){if(!d.kpis)return '';return `<div class="slim" style="--k:${d.kpis.length}">${d.kpis.map(k=>`<div><span>${esc(k.label)}</span><b>${esc(k.value)}</b>${k.note?`<small class="${k.tone||''}">${esc(k.note)}</small>`:''}</div>`).join('')}</div>`;}
function stripHTML(d){const s=d.stats,ks=kpisOf(d);
 let chip='',tone='';if(s.deltaText){chip=s.deltaText;tone=s.deltaTone||'';}else if(s.change!=null){chip=`${s.change>0?'+':s.change<0?'−':''}${Math.abs(s.change)}%% on the previous ${d.period} days`;tone=s.change>0?'up':s.change<0?'down':'';}
 const unit=d.kind==='heatmap'?'of 10':esc(d.unit);
 const cap=d.periodLabel?esc(d.periodLabel):'';
 return `<div class="strip" style="--k:${ks.length}"><div><div class="hero-line"><span class="ws-hero">${fmt(s.total)}<small>${unit}</small></span>${chip?`<span class="chip ${tone}">${esc(chip)}</span>`:''}</div><div class="hero-cap">${cap}</div></div>${ks.map(k=>`<div class="kpi"><div class="k-l">${esc(k.label)}</div><div class="k-v">${esc(k.value)}</div>${k.note?`<div class="k-n ${k.tone||''}">${esc(k.note)}</div>`:''}</div>`).join('')}</div>`;}

/* ---- next steps + stand-outs ---- */
function nextHTML(d,cap){const all=d.next||[];const n=cap?all.slice(0,cap):all;const more=all.length-n.length;const pats=[];
 const steps=n.length?`<ol class="steps">${n.map(s=>`<li class="st"><span class="sd ${s.impact||''}"></span><div><p class="st-t">${esc(s.t)}</p>${s.why?`<p class="st-w">${esc(s.why)}</p>`:''}<span class="st-o"><span>${esc(OWNER[s.owner]||'')}</span>${s.gain?`<b>+${s.gain.toFixed(2)} points</b>`:''}<span>${s.impact==='high'?'High impact':s.impact==='med'?'Medium impact':'Low impact'}</span></span></div></li>`).join('')}</ol>`:'<p class="empty-note">Nothing to act on right now.</p>';
 const so=pats.length?`<div><h3 class="ph">What stands out</h3><div class="so">${pats.map(p=>`<div class="so-i ${esc(p.type)}"><span>${esc(p.title)}</span>${esc(p.evidence)}</div>`).join('')}</div></div>`:'';
 const from=d._win&&d._win!=='7d'&&n.length?(/^Google/.test(d.source)?'from the 7-day review, ':d.source==='Site crawl'?'from the latest check, ':''):'';
 return `<div><h3 class="ph">Next steps<span>${more?`<button class="link-quiet more" data-detail="card">${more} more in All details</button>`:''}</span></h3>${steps}</div>${so}`;}

/* ---- one breakdown panel ---- */
function bdPanel(x){const rows=x.rows.slice(0,5),max=Math.max(1,...rows.map(r=>r.value));
 return `<section class="panel bdp"><h3 class="ph">${esc(x.title)}</h3><div class="hbars">${rows.map(r=>`<div class="hbar"><span title="${esc(r.label)}">${esc(r.label)}</span><div class="track"><div class="fill" data-w="${Math.max(1.5,100*r.value/max).toFixed(1)}"></div></div><strong>${fmt(r.value)}</strong></div>`).join('')}</div></section>`;}
/* ---- breakdowns ---- */
function bdsHTML(d){const b=(d.breakdowns||[]).filter(x=>x.rows&&x.rows.length).slice(0,3);if(!b.length)return '';
 return `<div class="bds" style="--b:${Math.max(2,b.length)}">${b.map(x=>{const rows=x.rows.slice(0,5),max=Math.max(1,...rows.map(r=>r.value));
  return `<section class="panel"><h3 class="ph">${esc(x.title)}</h3><div class="hbars">${rows.map(r=>`<div class="hbar"><span title="${esc(r.label)}">${esc(r.label)}</span><div class="track"><div class="fill" data-w="${Math.max(1.5,100*r.value/max).toFixed(1)}"></div></div><strong>${fmt(r.value)}</strong></div>`).join('')}</div></section>`;}).join('')}</div>`;}

/* ---- launch marker: one thin line where the new site went live ---- */
const LAUNCH='2026-11-15';
function launchMark(id,d,kind){const frame=el(id),svg=frame?.querySelector('svg');if(!svg)return;const dates=d.main.dates,i=dates.indexOf(LAUNCH);if(i<0||!d.main.previous)return;
 const vb=svg.viewBox.baseVal,W=vb.width,H=vb.height,L=44,R=12,T=kind==='cols'?18:14,B=30,n=dates.length;
 const x=kind==='cols'?L+(W-L-R)/n*i:L+(n===1?0.5:i/(n-1))*(W-L-R);
 const g=document.createElementNS('http://www.w3.org/2000/svg','g');g.setAttribute('class','launch');
 g.innerHTML=`<line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${T}" y2="${H-B}"/><text x="${(x>W*0.8?x-6:x+6).toFixed(1)}" y="${T+10}" text-anchor="${x>W*0.8?'end':'start'}">New site</text>`;
 svg.insertBefore(g,svg.firstChild.nextSibling);}

/* ---- early figures: soft band over days Google has not finalised ---- */
function earlyMark(id,d,kind){const e=d.main.earlyFrom;if(!e)return;const frame=el(id),svg=frame?.querySelector('svg');if(!svg)return;const dates=d.main.dates,i=dates.indexOf(e);if(i<0)return;
 const vb=svg.viewBox.baseVal,W=vb.width,H=vb.height,L=44,R=12,T=kind==='cols'?18:14,B=30,n=dates.length,step=(W-L-R)/(kind==='cols'?n:Math.max(1,n-1));
 const x0=kind==='cols'?L+step*i:Math.max(L,L+step*(i-.5)),x1=W-R;
 const g=document.createElementNS('http://www.w3.org/2000/svg','g');g.setAttribute('class','early');
 const bk=d.main.bucket,lbl=bk==='minute'?'Filling':'Early',why=bk==='minute'?'This minute is still filling':`Early figures: Google is still counting these ${bk==='hour'?'hours':'days'}`;
 g.innerHTML=`<title>${why}</title><rect x="${x0.toFixed(1)}" y="${T}" width="${(x1-x0).toFixed(1)}" height="${H-B-T}" rx="6"/><text x="${(x1-6).toFixed(1)}" y="${T+10}" text-anchor="end">${lbl}</text>`;
 svg.insertBefore(g,svg.firstChild);}

/* ---- page speed: pages slowest first; a page opens its size by file type ---- */
const SITE_URL='https://fnbperformance.com';
const msTone=(ms)=>ms>=1000?'bad':ms>=500?'warn':'';
function pagesPanel(d){const P=d.pages||[],mx=Math.max(1,...P.map(p=>p.ms));
 return `<section class="panel pgp"><h3 class="ph">Pages, slowest first<span>${P.length} pages</span></h3><div class="pgl"><div>
  <div class="pgh"><span>Page</span><span>Response</span><span>ms</span><span>KB</span><span>Heaviest</span></div>
  ${P.map(p=>`<button class="pgr" data-page="${esc(p.path)}" title="${esc(p.path)}"><span class="pgn">${esc(p.name)}</span><span class="pgb"><i style="width:${Math.max(2,100*p.ms/mx).toFixed(1)}%%"></i></span><b class="${msTone(p.ms)}">${fmt(p.ms)}</b><em>${fmt(p.kb)}</em><small>${esc(p.types[0]?.[0]||'')}</small></button>`).join('')}</div></div></section>`;}
function pageSheet(d,p){const tot=Math.max(1,p.kb),top=p.types[0],pct=(v)=>Math.round(100*v/tot)+'%%';
 return HEAD(`Page speed, ${p.path}`,p.name,PILL(msTone(p.ms)||'good',`${fmt(p.ms)} ms response`))+`<div class="pp">
  ${BOX('Reading',KV([{label:'Response',value:fmt(p.ms)+' ms'},{label:'Page size',value:fmt(p.kb)+' KB'},{label:'Files',value:fmt(p.n)}]))}
  ${BOX('By file type<span>KB, share of the page</span>',`<div class="ftl">${p.types.map((t,i)=>`<div class="ftr${i===0?' top':''}"><span>${esc(t[0])}</span><span class="tr"><span class="fl" style="width:${Math.max(2,100*t[1]/top[1]).toFixed(1)}%%"></span></span><b>${fmt(t[1])}</b><em>${pct(t[1])}</em></div>`).join('')}</div>`)}
  ${p.files?.length?BOX('Largest files',p.files.map(f=>`<div class="lr"><span title="${esc(f[0])}">${esc(f[0])}<small>${esc(f[1])}</small></span><b>${fmt(f[2])} KB</b></div>`).join('')):''}
  <div class="pbtns"><a class="pbtn primary" href="${esc(SITE_URL+p.path)}" target="_blank" rel="noopener">Open page ↗</a><button class="pbtn" data-detail-close>Close</button></div>
 </div>`;}
function openPage(path,opener){const d=BY[cur],p=(d?.pages||[]).find(x=>x.path===path);if(!p)return;detailOpener=opener;const panel=el('detailPanel'),scrim=el('detailScrim'),body=el('detailBody');
 state.detail={metric:'page',data:{raw:null}};panel.classList.add('sheet','pg');body.innerHTML=pageSheet(d,p);
 scrim.hidden=false;panel.hidden=false;document.body.classList.add('detail-open');detailClosing=false;
 requestAnimationFrame(()=>{scrim.classList.add('on');panel.classList.add('on');});body.focus({preventScroll:true});}

/* ---- columns chart (small daily counts) ---- */
function colChart(id,d){const frame=el(id),ser=Object.values(d.main.series)[0],cur=ser.map(p=>p?.value??null),prev=(d.main.previous||[]).map(p=>p?.value??null),dates=d.main.dates;
 const W=Math.max(280,frame.clientWidth||700),H=Math.max(180,frame.clientHeight||300),L=44,R=12,T=18,B=30,n=cur.length;
 const nn=(a)=>a.filter(v=>v!=null),part=new Set(d.main.partial||[]),mx=Math.max(0,...nn(cur));
 const top=niceTop(Math.max(1,...nn(cur),...nn(prev))*1.15),y=v=>T+(1-v/top)*(H-T-B),slot=(W-L-R)/n,bw=Math.min(30,slot*(n>14?.5:.34));
 const every=Math.max(1,Math.ceil(n/(W<520?4:8))),showVal=(v,i)=>v&&(n<=14||(v===mx&&cur.indexOf(mx)===i));
 const grid=[0,.25,.5,.75,1].map(t=>`<line class="chart-grid" x1="${L}" x2="${W-R}" y1="${y(top*t).toFixed(1)}" y2="${y(top*t).toFixed(1)}"/><text class="chart-axis" x="${L-12}" y="${(y(top*t)+4).toFixed(1)}" text-anchor="end">${fmt(top*t)}</text>`).join('');
 let bars='';cur.forEach((v,i)=>{const cx=L+slot*(i+.5),lab=(i%%every===0||(i===n-1&&(n-1)%%every>=every*.6))?`<text class="chart-axis" x="${cx.toFixed(1)}" y="${H-6}" text-anchor="middle">${esc(shortDate(dates[i]))}</text>`:'';
  const tip=`${esc(nice(dates[i]))}: ${v==null?'not recorded':fmt(v)}${part.has(i)?' (partly recorded)':''}${d.main.earlyFrom&&dates[i]>=d.main.earlyFrom?(d.main.bucket==='minute'?' (still filling)':' (early)'):''}${prev.length?`, ${esc(d.main.tipLabel||'previous')} ${prev[i]==null?'not recorded':fmt(prev[i])}`:''}`;
  if(v==null){bars+=`<g><title>${tip}</title><rect class="col-gap" x="${(cx-bw/2).toFixed(1)}" y="${(y(0)-10).toFixed(1)}" width="${bw.toFixed(1)}" height="10" rx="3"/>${lab}</g>`;return;}
  const h=Math.max(v?2:0,y(0)-y(v));
  bars+=`<g><title>${tip}</title><rect class="col-cur${part.has(i)?' col-part':''}" x="${(cx-bw/2).toFixed(1)}" y="${(y(0)-h).toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" rx="${n>14?3:4}"/>${showVal(v,i)?`<text class="col-val" x="${cx.toFixed(1)}" y="${(y(v)-7).toFixed(1)}" text-anchor="middle">${fmt(v)}</text>`:''}${lab}</g>`;});
 const pts=prev.map((v,i)=>v==null?null:`${(L+slot*(i+.5)).toFixed(1)},${y(v).toFixed(1)}`);
 const runs=[];let rr=[];pts.forEach(q=>{if(q==null){if(rr.length)runs.push(rr);rr=[];}else rr.push(q);});if(rr.length)runs.push(rr);
 const ghost=n>14&&prev.length?prev.map((v,i)=>{if(!v)return '';const cx=L+slot*(i+.5),h=Math.max(2,y(0)-y(v));return `<rect class="col-prev" x="${(cx-bw/2-1.5).toFixed(1)}" y="${(y(0)-h).toFixed(1)}" width="${(bw+3).toFixed(1)}" height="${h.toFixed(1)}" rx="3"/>`;}).join(''):'';
 const pl=n>14?'':prev.length?runs.map(r=>`<polyline class="col-trend" points="${r.join(' ')}"/>`).join('')+nn(pts).map(q=>{const[a,b]=q.split(',');return `<circle class="col-dot" cx="${a}" cy="${b}" r="2.2"/>`}).join(''):'';
 const quiet=!mx&&!nn(prev).some(v=>v)?`<text class="col-empty" x="${((L+W-R)/2).toFixed(1)}" y="${((T+H-B)/2).toFixed(1)}" text-anchor="middle">No ${esc(d.unit)} in the last ${esc(WNAME[d._win]||'period')}</text>`:'';
 frame.innerHTML=`<svg role="img" aria-label="${esc(d.unit)} as columns, dotted line is ${esc(d.main.tipLabel||'the previous period')}" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">${grid}${ghost}${bars}${pl}${quiet}</svg>`;}

/* ---- heatmap: names and audit pinned left, target pinned right; 7 days in view, earlier days scroll left ---- */
let HS=0;
const addDays=(iso,n)=>{const t=new Date(iso.slice(0,10)+'T12:00:00Z');t.setUTCDate(t.getUTCDate()+n);return t.toISOString().slice(0,10);};
function heatmap(id,d){const f=el(id),h=d.heat,one=(v)=>v===null||v===undefined?'--':Number(v).toFixed(1);
 const nd=h.cols.length-1,iso=(h.dates||d.main.dates||[]),IV=h.inview||7,STEP=h.step||1,dense=h.mode==='dense',off=dense?Math.max(0,nd-IV):0,days=iso.slice(1+off,1+nd),L=META.launch||'2026-11-15',UN=STEP===7?'weeks':'days';
 const stages=h.stages||['Launch','Establish','Grow','Mature'].map((nm,i)=>({name:nm,until:i<3?addDays(L,7*i+6):null}));
 const stageOf=(x)=>(stages.find(s=>!s.until||x<=s.until)||stages[stages.length-1]).name;
 const fut=[];for(let k=days.length;k<IV;k++)fut.push(addDays(days[days.length-1]||L,(k-days.length+1)*STEP));
 const all=[...days,...fut],N=all.length,now=days.length-1,st=all.map(stageOf),curStage=st[Math.max(0,now)];
 const bnd=all.map((x,i)=>i>0&&st[i]!==st[i-1]);
 const segs=[];all.forEach((x,i)=>{if(i===0||bnd[i])segs.push({name:st[i],k:1,i});else segs[segs.length-1].k++;});
 const stageRow=`<div class="heat-row stage" aria-hidden="true"><span class="lead"></span>${segs.map(g=>`<span class="stg${g.name===curStage?' cur':''}" style="grid-column:span ${g.k}"><span class="sl">${esc(g.name)}</span></span>`).join('')}<span class="tg"></span></div>`;
 const head=`<div class="heat-row head"><span class="lead"><span>Block, weight</span><span class="hc">Audit</span></span>${all.map((x,i)=>`<span class="hc${i>now?' fut':''}">${esc(dense&&i%%7?'':i<=now?h.cols[i+1+off]:shortDate(x))}</span>`).join('')}<span class="tg">Target</span></div>`;
 const rows=h.rows.map(r=>{const tg=(i)=>(r.targets&&r.targets[i]!=null)?r.targets[i]:r.target;
  const audit=`<span class="cell ${r.cells[0]==null?'none':r.bands[0]}" title="Audit, Nov 13: ${one(r.cells[0])}">${one(r.cells[0])}</span>`;
  const cells=all.map((x,i)=>{if(i>now)return `<span class="cell slot" title="${STEP===7?'Week of ':''}${esc(shortDate(x))}: next snapshots"></span>`;const j=i+1+off,v=r.cells[j];
   return `<span class="cell ${v===null||v===undefined?'none':r.bands[j]}${i===now?' now':''}" title="${esc(h.spans?h.spans[j]:h.cols[j])}: ${one(v)}${STEP===7?' average':''}, ${esc(st[i])} target ${one(tg(j))}">${dense?'':one(v)}</span>`;}).join('');
  return `<button class="heat-row" data-sheet="${esc(r.id)}" aria-haspopup="dialog"><span class="lead"><span class="nm">${esc(r.name)}<small>${r.weight}%%</small></span>${audit}</span>${cells}<span class="tg">${one(r.target)}</span></button>`;}).join('');
 const lines=all.map((x,i)=>bnd[i]?`<i class="sline" style="left:calc(var(--nw) + 6px + var(--aw) + var(--gp) + ${i} * (var(--cw) + var(--gp)) - var(--gp) / 2 - .5px)"></i>`:'').join('');
 const key='';
 f.innerHTML=`<div class="heat"><div class="hscroll"><div class="hgrid${dense?' dense':''}" style="--n:${N}">${lines}${stageRow}${head}${rows}</div></div>${key}</div>`;
 const box=f.querySelector('.heat'),sc=f.querySelector('.hscroll'),g=f.querySelector('.hgrid'),hint=document.createElement('span');
 const W=sc.clientWidth;let cw,nw,aw,gp=6;
 if(dense){gp=3;aw=44;nw=Math.round(Math.max(190,Math.min(240,W*.25)));cw=Math.max(12,Math.floor((W-nw-6-aw-52-gp*(IV+1)-4)/IV));}
 else{cw=Math.max(40,Math.min(66,Math.floor((W-106-210)/(IV+1))));aw=cw;nw=Math.max(140,W-106-(IV+1)*cw);}
 g.style.setProperty('--cw',cw+'px');g.style.setProperty('--nw',nw+'px');g.style.setProperty('--aw',aw+'px');g.style.setProperty('--gp',gp+'px');
 const max=()=>Math.max(0,sc.scrollWidth-sc.clientWidth);
 const mark=()=>{const l=sc.scrollLeft>1,r=max()-sc.scrollLeft>1;box.classList.toggle('more-l',l);box.classList.toggle('more-r',r);hint.textContent=l?`Earlier ${UN} to the left`:r?`Later ${UN} to the right`:'';HS=max()-sc.scrollLeft;};
 
 sc.scrollLeft=Math.max(0,max()-HS);mark();sc.addEventListener('scroll',mark,{passive:true});
 sc.addEventListener('wheel',e=>{if(max()<1)return;const dx=Math.abs(e.deltaX)>Math.abs(e.deltaY)?e.deltaX:e.deltaY,nx=Math.max(0,Math.min(max(),sc.scrollLeft+dx));if(nx===sc.scrollLeft)return;e.preventDefault();sc.scrollLeft=nx;},{passive:false});
 let x0=null,l0=0,moved=false;
 sc.addEventListener('pointerdown',e=>{if(e.pointerType!=='mouse'||e.button!==0||max()<1)return;x0=e.clientX;l0=sc.scrollLeft;moved=false;});
 sc.addEventListener('pointermove',e=>{if(x0===null)return;const dx=e.clientX-x0;if(!moved&&Math.abs(dx)>4){moved=true;sc.setPointerCapture(e.pointerId);sc.classList.add('drag');}if(moved)sc.scrollLeft=l0-dx;});
 const end=()=>{x0=null;sc.classList.remove('drag');};sc.addEventListener('pointerup',end);sc.addEventListener('pointercancel',end);
 sc.addEventListener('click',e=>{if(moved){e.stopPropagation();e.preventDefault();moved=false;}},true);}

/* ---- block popup ---- */
const PILL=(tone,t)=>`<span class="pill ${tone}">${esc(t)}</span>`;
const KV=(items)=>`<div class="kv">${items.filter(Boolean).map(k=>`<div><span>${esc(k.label)}</span><b class="${k.tone||''}">${esc(k.value)}</b>${k.note?`<small>${esc(k.note)}</small>`:''}</div>`).join('')}</div>`;
const BOX=(title,inner,extra='')=>`<section class="box ${extra}"><h4>${title}</h4>${inner}</section>`;
const HEAD=(kicker,title,pill='')=>`<div class="pp-head"><div class="ph-t"><h2 class="detail-title" id="detailTitle">${esc(title)}</h2>${pill}<span class="ph-k">${esc(kicker)}</span></div>${CLOSE_BTN}</div>`;
const IDS={'Site health, Pages live':'pages','Site health, Broken links':'broken','Site health, Server response time':'response','Site health, Home page size':'weight','Site health, Page speed':'speed','Site health, Pages with issues':'issues','Authority, Referring domains':'refdomains','Authority, Authority score':'authority','Google Search, Search impressions':'impressions','Google Search, Keywords on page one':'pageone','Enquiries, Profit Review requests':'leads','Enquiries, WhatsApp clicks':'whatsapp','Enquiries, Calculator uses':'tools'};
function sheetHTML(d,r){const one=(v)=>v===null||v===undefined?'--':Number(v).toFixed(1),now=r.cells.at(-1),gap=r.target-now,ok=gap<=0.05;
 const subs=[...r.subs].map(s=>({...s,gain:r.weight*s.weight*Math.max(0,r.target-s.score)/10000})).sort((a,b)=>b.gain-a.gain);
 const gainAll=subs.reduce((a,s)=>a+s.gain,0),live=subs.filter(s=>s.measured).length;
 const cards=(d.blocks?.[r.id]?.questions||[]).find(q=>q.id==='cards')?.answer?.items||[];
 const acts=subs.filter(s=>s.band!=='good'&&s.action);
 return HEAD(`Search visibility, ${d.heat.stage} stage`,r.name,PILL(ok?'good':'bad',ok?`On target at ${one(now)}`:`${one(gap)} below the ${one(r.target)} target`))+`<div class="pp">
  ${BOX('Score',KV([{label:'Now',value:one(now)},{label:'Target',value:one(r.target)},{label:'Audit, Nov 13',value:one(r.cells[0])},{label:'Weight',value:r.weight+'%%'},{label:'Points to gain',value:'+'+gainAll.toFixed(2),tone:gainAll>0?'up':''}]))}
  ${BOX(`Sub-metrics<span>${live} of ${subs.length} measured live</span>`,`<div class="sml">${subs.map(s=>`<div class="smr" title="${esc(s.evidence||'')}"><span class="smn">${esc(s.name)}<em>${s.measured?'live':'audit'}</em></span><span class="sbar"><span class="tr"><span class="fl ${s.band}" style="display:block;width:${Math.max(2,s.score*10)}%%"></span></span><b>${one(s.score)}</b></span><span class="smw">${s.weight}%%</span>${s.evidence?`<span class="sme">${esc(s.evidence)}</span>`:''}</div>`).join('')}</div>`)}
  ${acts.length?BOX('Next actions',`<ol class="acts">${acts.map(s=>`<li><span class="sd ${s.gain>=0.1?'high':s.gain>=0.04?'med':''}"></span><span class="at">${esc(s.action)}</span><span class="ao">${esc(OWNER[s.owner]||'')}${s.gain>=0.005?` <b>+${s.gain.toFixed(2)}</b>`:''}</span></li>`).join('')}</ol>`):''}
  ${cards.length?`<div class="pbtns">${cards.map((c,i)=>IDS[c]?`<button class="pbtn${i===0?' primary':''}" data-goto="${IDS[c]}">${esc(c.split(', ')[1]||c)} ↗</button>`:'').join('')}</div>`:''}
 </div>`;}
/* ---- All details popup ---- */
function detailHTML(d){const q=(id)=>(d.questions||[]).find(x=>x.id===id)?.answer;
 const src=q('source'),cav=q('caveats'),ks=kpisOf(d),s=d.stats;
 const caution=(d.patterns||[]).find(p=>p.type==='caution');
 const pill=caution?PILL('warn',caution.title):PILL('good',`Live, data through ${shortDate(d.through)}`);
 const reading=[{label:'Total',value:fmt(s.total)+(d.kind==='heatmap'?' of 10':' '+d.unit)},s.deltaText?{label:'Change',value:s.deltaText,tone:s.deltaTone}:s.change!=null?{label:'Change',value:`${s.change>0?'+':''}${s.change}%%`,note:`on the previous ${d.period} days`,tone:s.change>0?'up':s.change<0?'down':''}:null,...ks];
 const pats=(d.patterns||[]).filter(p=>p.type!=='movement').slice(0,4);
 const bds=(d.breakdowns||[]).filter(b=>b.rows&&b.rows.length);
 const srcRow=src?.rows?.[0]||[];
 return HEAD(`${d.group||''}, ${d.periodLabel||''}`,d.label,pill)+`<div class="pp">
  ${BOX('Reading',KV(reading))}
  ${pats.length?BOX('What stands out',`<div class="pl">${pats.map(p=>`<div><span class="pd ${esc(p.type)}"></span><span><b>${esc(p.title)}</b><small>${esc(p.evidence)}</small></span></div>`).join('')}</div>`):''}
  ${bds.length?BOX('Breakdowns',`<div class="bdg">${bds.map(b=>`<div><h5>${esc(b.title)}</h5>${b.rows.slice(0,6).map(r=>`<div class="lr"><span title="${esc(r.label)}">${esc(r.label)}</span><b>${fmt(r.value)}</b></div>`).join('')}</div>`).join('')}</div>`):''}
  ${(d.next||[]).length?BOX('Next steps',`<ol class="acts">${d.next.map(n=>`<li><span class="sd ${n.impact||''}"></span><span class="at">${esc(n.t)}</span><span class="ao">${esc(OWNER[n.owner]||'')}${n.gain?` <b>+${n.gain.toFixed(2)}</b>`:''}</span></li>`).join('')}</ol>`):''}
  ${BOX('Source',KV([{label:'Feed',value:srcRow[0]||d.source||''},{label:'Window',value:d.periodLabel||''},{label:'Data through',value:shortDate(d.through)}])+`<p class="pnote">${esc(d.howCalculated||'')}</p>${cav?.items?.length?`<ul class="cav">${cav.items.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}`)}
  <div class="pbtns">${d.raw?.rows?.length?`<button class="pbtn primary" data-copy-csv>Copy data as CSV</button>`:''}<button class="pbtn" data-detail-close>Close</button></div>
  ${d.raw?.rows?.length?`<details class="disc"><summary>Raw data and fields</summary><p class="pnote">Fields: ${esc(srcRow[1]||'')}</p>${miniTable(d.raw.columns,d.raw.rows.slice(0,60).map(r=>r.map(c=>typeof c==='number'?fmt(c):c??'')))}</details>`:''}
 </div>`;}
function openSheet(bid,opener){const d=BY[cur],r=d?.heat?.rows.find(x=>x.id===bid);if(!r)return;detailOpener=opener;const panel=el('detailPanel'),scrim=el('detailScrim'),body=el('detailBody');
 state.detail={metric:bid,data:{raw:null}};panel.classList.add('sheet');body.innerHTML=sheetHTML(d,r);
 scrim.hidden=false;panel.hidden=false;document.body.classList.add('detail-open');detailClosing=false;
 requestAnimationFrame(()=>{scrim.classList.add('on');panel.classList.add('on');});body.focus({preventScroll:true});}

/* ---- workspace ---- */
function chartHeading(d){if(d.kind==='heatmap')return `Blocks against the ${esc(d.heat.stage)} stage target`;
 const p=d.main.previous;const label=d.main.tipLabel||'previous period';
 if(isCols(d))return esc(d.main.heading||headingOf(d));
 return esc(d.main.heading||headingOf(d));}
function isCols(d){if(d.level||d.kind)return false;const v=[...Object.values(d.main.series)[0].map(p=>p?.value||0),...(d.main.previous||[]).map(p=>p?.value||0)];return Math.max(...v)<=10;}
function drawCard(animate=true){if(!BY[cur])return;const d=view(BY[cur]);CUR_STEP=d.main.step||0;const ws=el('ws');const B=(d.breakdowns||[]).filter(x=>x.rows&&x.rows.length).slice(0,3);
 ws.innerHTML=`${headHTML(d)}
 ${slimStrip(d)}
 ${d.kind==='heatmap'?(()=>{const H=(d.breakdowns||[]).filter(x=>x.rows&&x.rows.length&&!/^Points to gain|^Blocks/.test(x.title)).slice(0,3);
 return `<div class="r1 tight hm"><section class="panel"><h3 class="ph">${chartHeading(d)}</h3><div id="analyticsChart"></div></section><aside class="panel np">${nextHTML(d)}</aside></div>
 ${H.length?`<div class="r3" style="--k:${H.length}">${H.map(bdPanel).join('')}</div>`:''}`;})()
 :d.pages?`<div class="r1 sp"><section class="panel"><h3 class="ph">${chartHeading(d)}</h3><div id="analyticsChart" class="chart-frame ws-chart"></div></section>${pagesPanel(d)}</div>
 <div class="r2${B[0]?' has3':''}"><aside class="panel np">${nextHTML(d)}</aside>${B[0]?bdPanel(B[0]):''}</div>`
 :`<div class="r1" style="--k:${Math.min(2,B.length)}"><section class="panel"><h3 class="ph">${chartHeading(d)}</h3><div id="analyticsChart" class="chart-frame ws-chart"></div></section>${B.slice(0,2).map(bdPanel).join('')}</div>
 <div class="r2${B[2]?' has3':''}"><aside class="panel np">${nextHTML(d)}</aside>${B[2]?bdPanel(B[2]):''}</div>`}`;
 if(d.kind==='heatmap'){heatmap('analyticsChart',d);const nb=ws.querySelector('.r1.hm>.np>div');if(nb){const fb=()=>nb.classList.toggle('fade-b',nb.scrollHeight-nb.clientHeight-nb.scrollTop>2);fb();nb.addEventListener('scroll',fb,{passive:true});}}
 else if(isCols(d)){colChart('analyticsChart',d);launchMark('analyticsChart',d,'cols');earlyMark('analyticsChart',d,'cols');}
 else{const key=Object.keys(d.main.series)[0];lineChart('analyticsChart',{dates:d.main.dates,series:d.main.series,unit:d.unit,animate,ghost:d.main.previous?{[key]:d.main.previous}:null,ghostLabel:d.main.tipLabel||'Previous period'});launchMark('analyticsChart',d,'line');earlyMark('analyticsChart',d,'line');}
 fillBars(ws);}
/* ---- time windows (Checkpoint 27): one toggle for every card ---- */
const WINS=['30m','12h','24h','7d','30d','all'],SHORT=new Set(['30m','12h','24h']);
const WLAB={'30m':'30m','12h':'12h','24h':'24h','7d':'7d','30d':'30d','all':'All'};
const WNAME={'30m':'30 minutes','12h':'12 hours','24h':'24 hours','7d':'7 days','30d':'30 days','all':'since launch'};
const LIVE_URL='https://raw.githubusercontent.com/RavenArtStudio/fnb-monitor/live/data/live.json';
let WIN='7d',LIVE=null,SNAP_MODE='saved',CUR_STEP=0;
try{const q=new URLSearchParams(location.search).get('w'),m=localStorage.getItem('fnb-window');WIN=WINS.includes(q)?q:WINS.includes(m)?m:'7d';}catch(e){}
function tlab(iso,day){const t=new Date(iso);if(isNaN(t))return iso;const hm=t.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});return day?t.toLocaleDateString('en-US',{month:'short',day:'numeric'})+', '+hm:hm;}
function tipT(iso){const s=CUR_STEP>1?' to '+tlab(new Date(Date.parse(iso)+CUR_STEP*60000).toISOString().slice(0,16)+'Z',false):'';return tlab(iso,true)+s;}
function headingOf(d){const b=d.main.bucket;return b==='minute'?'Minute by minute':b==='hour'?'Hour by hour':b==='check'?'Check by check':'Day by day';}
function winsOf(d){if(d.fixed)return [];return d.wins&&d.wins.length?d.wins:['7d'];}
function served(d){const ws=winsOf(d);if(!ws.length)return null;if(ws.includes(WIN))return WIN;const i=WINS.indexOf(WIN);
 for(const k of WINS.slice(i+1))if(ws.includes(k))return k;for(const k of WINS.slice(0,i).reverse())if(ws.includes(k))return k;return ws[0];}
function view(d){const k=served(d),b=k&&k!=='7d'&&d.w?d.w[k]:null,v=Object.assign({},d,b||{});v._win=k;v._live=!!(b&&SHORT.has(k)&&d.source==='Google Analytics');return v;}
const liveStale=()=>!LIVE?.meta||Date.now()-Date.parse(LIVE.meta.generated)>45*60000;
function whyNot(d){if(d.id==='engaged')return 'Google gives no live engagement figure.';const s=d.source;
 if(s==='Google Analytics')return LIVE?'The live feed has no reading for this window.':'The live feed is not loaded yet.';
 if(s==='Google Search Console')return WIN==='30m'?'Google reports search by the hour at best, and hours late.':'';
 if(s==='Site crawl')return 'The site is checked about every 3 hours.';if(s==='Cube')return 'The score is worked out once per snapshot.';return '';}
function wnote(d){if(d.fixed)return null;
 if(d._win&&d._win!==WIN)return {t:`Showing ${WNAME[d._win]}`,c:'fb'};
 if(d._live&&liveStale())return {t:`Live feed paused since ${LIVE?.meta?tlab(LIVE.meta.minute,true):'--'}`,c:'warn'};
 return null;}
function mergeLive(){if(!LIVE?.cards)return;for(const id in LIVE.cards){const c=BY[id],L=LIVE.cards[id];if(!c)continue;
 c.w=Object.assign({},c.w||{},L.w);const s=new Set([...(c.wins||['7d']),...(L.wins||[])]);c.wins=WINS.filter(k=>s.has(k));}}
function snapLine(){const lv=LIVE?.meta?`<span class="sn ${liveStale()?'saved':'live'}" title="Google Analytics live feed, saved every 15 minutes"><i></i>Live ${esc(tlab(LIVE.meta.minute,true))}</span>`:'';
 el('snap').innerHTML=`<span class="sn ${SNAP_MODE}"><i></i>Snapshot ${esc(META.generated?when(META.generated):'not taken yet')}${SNAP_MODE==='saved'?', saved copy':''}</span>${lv}`;}
function markWin(){const d=BY[cur],ws=d?winsOf(d):[],v=d?view(d):null;
 document.querySelectorAll('.win-tg button').forEach(b=>{const k=b.dataset.win,on=k===WIN;b.setAttribute('aria-pressed',String(on));
  b.classList.toggle('na',!!d&&!d.fixed&&!ws.includes(k));b.classList.toggle('shown',!!v&&!d.fixed&&v._win===k&&!on);
  b.title=`${WNAME[k]}${d&&!d.fixed&&!ws.includes(k)?', not measured for this card':''}  (key ${WINS.indexOf(k)+1})`;});
 el('wintg').classList.toggle('off',!!d?.fixed);}
function setWin(k){if(!WINS.includes(k)||k===WIN)return;WIN=k;HS=0;try{localStorage.setItem('fnb-window',k);const u=new URL(location.href);if(u.searchParams.has('w')){u.searchParams.delete('w');history.replaceState(null,'',u.pathname+u.search+u.hash);}}catch(e){}
 drawRail();drawCard();markWin();if(SHORT.has(k)&&liveStale())loadLive();}
function loadLive(){return fetch(LIVE_URL+'?t='+Date.now(),{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(r.status)).then(j=>{if(!j?.meta)return;
 if(!LIVE?.meta||j.meta.generated>=LIVE.meta.generated){LIVE=j;mergeLive();snapLine();drawRail();drawCard(false);markWin();}}).catch(()=>{});}
el('wintg').innerHTML=WINS.map((k,i)=>`<button type="button" data-win="${k}" aria-pressed="${k===WIN}">${WLAB[k]}</button>`).join('');
el('wintg').addEventListener('click',e=>{const b=e.target.closest('button[data-win]');if(b)setWin(b.dataset.win);});
document.addEventListener('keydown',e=>{if(e.metaKey||e.ctrlKey||e.altKey||!el('detailPanel').hidden||/INPUT|TEXTAREA|SELECT/.test(e.target.tagName||''))return;
 const n=Number(e.key);if(n>=1&&n<=6){e.preventDefault();setWin(WINS[n-1]);}});
setInterval(()=>{if(document.visibilityState==='visible'&&SHORT.has(WIN))loadLive();},180000);
setInterval(()=>{if(LIVE)snapLine();},60000);
function setData(j,mode){META=j.meta||{};CARDS=j.cards||[];ORDER=CARDS.map(c=>c.id);BY=Object.fromEntries(CARDS.map(c=>[c.id,c]));
 const h=location.hash.slice(1);if(!ORDER.includes(cur))cur=ORDER.includes(h)?h:ORDER[0];
 SNAP_MODE=mode;mergeLive();snapLine();
 const notes=(META.notes||[]).join(' ');el('note').textContent=(notes?notes+' ':'')+(mode==='saved'?'Showing the copy saved in this file; the latest snapshot could not be loaded.':'');
 drawRail();drawCard();markWin();}
function pick(id,focus){cur=id;history.replaceState(null,'','#'+id);document.querySelectorAll('.rail-item').forEach(b=>{const on=b.dataset.card===id;b.setAttribute('aria-selected',String(on));b.tabIndex=on?0:-1;if(on&&focus)b.focus();});drawCard();markWin();}
detailOpener=null;detailClosing=false;
function showDetail(d,metric,opener){detailOpener=opener;const panel=el('detailPanel'),scrim=el('detailScrim'),body=el('detailBody');
 state.detail={metric,data:d};panel.classList.add('sheet');body.innerHTML=detailHTML(d);
 scrim.hidden=false;panel.hidden=false;document.body.classList.add('detail-open');detailClosing=false;
 requestAnimationFrame(()=>{scrim.classList.add('on');panel.classList.add('on');});body.focus({preventScroll:true});}
function closeDetail(){const panel=el('detailPanel'),scrim=el('detailScrim');if(panel.hidden||detailClosing)return;detailClosing=true;
 panel.classList.remove('on');scrim.classList.remove('on');document.body.classList.remove('detail-open');
 setTimeout(()=>{if(!panel.classList.contains('on')){panel.hidden=true;scrim.hidden=true;panel.classList.remove('sheet','pg');el('detailBody').innerHTML='';state.detail=null;}detailClosing=false;},reduceMotion?0:420);
 if(detailOpener&&document.contains(detailOpener))detailOpener.focus({preventScroll:true});}
document.addEventListener('click',e=>{
 const t=e.target.closest('[data-card],[data-page],[data-sheet],[data-goto],[data-detail],[data-detail-close],[data-intent],[data-q],[data-raw],[data-copy-csv]');if(!t)return;
 if(t.dataset.card){pick(t.dataset.card);return;}
 if(t.dataset.page){openPage(t.dataset.page,t);return;}
 if(t.dataset.sheet){openSheet(t.dataset.sheet,t);return;}
 if(t.dataset.goto){const id=t.dataset.goto;detailOpener=null;closeDetail();pick(id,true);return;}
 if(t.dataset.detail){showDetail(view(BY[cur]),'card',t);return;}
 if(t.hasAttribute('data-detail-close')){closeDetail();return;}
 const s=state.detail;if(!s?.data)return;
 if(t.dataset.intent){s.intent=t.dataset.intent;s.open=s.data.questions.find(q=>q.intent===s.intent)?.id||null;renderAsk();return;}
 if(t.dataset.q){s.open=s.open===t.dataset.q?null:t.dataset.q;renderAsk();return;}
 if(t.hasAttribute('data-raw')){const b=el('rawBlock'),open=b.hidden;b.hidden=!open;t.setAttribute('aria-expanded',String(open));t.textContent=open?'Hide the data':'Show the data';return;}
 if(t.hasAttribute('data-copy-csv')){const csv=[s.data.raw.columns,...s.data.raw.rows].map(r=>r.map(csvCell).join(',')).join('\n');
  (navigator.clipboard?.writeText(csv)||Promise.reject()).then(()=>toast('Copied as CSV')).catch(()=>toast('Copying is blocked here; select the table instead'));}
});
el('detailScrim').addEventListener('click',()=>closeDetail());
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!el('detailPanel').hidden){e.preventDefault();closeDetail();return;}
 if(!el('detailPanel').hidden||!e.target.closest?.('.rail'))return;const i=ORDER.indexOf(cur);
 if(e.key==='ArrowDown'||e.key==='ArrowRight'){e.preventDefault();pick(ORDER[(i+1)%%ORDER.length],true);}
 if(e.key==='ArrowUp'||e.key==='ArrowLeft'){e.preventDefault();pick(ORDER[(i-1+ORDER.length)%%ORDER.length],true);}});
let rz;window.addEventListener('resize',()=>{clearTimeout(rz);rz=setTimeout(()=>drawCard(false),150);});
function setTheme(t,save){document.documentElement.classList.toggle('paper',t==='paper');document.querySelectorAll('.theme-tg button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.theme===t)));
 if(save){try{localStorage.setItem('fnb-theme',t);}catch(e){}try{const u=new URL(location.href);if(u.searchParams.has('theme')){u.searchParams.delete('theme');history.replaceState(null,'',u.pathname+u.search+u.hash);}}catch(e){}}}
document.querySelectorAll('.theme-tg button').forEach(b=>b.addEventListener('click',()=>{if(b.getAttribute('aria-pressed')==='true')return;setTheme(b.dataset.theme,true);drawCard(false);markWin();}));
setTheme(document.documentElement.classList.contains('paper')?'paper':'charcoal',false);
LIVE=SAVED_LIVE;
setData(SAVED,'saved');
loadLive();
fetch(SNAP_URL+'?t='+Date.now(),{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(r.status)).then(j=>setData(j,'live')).catch(()=>{});
''' % (json.dumps(saved, ensure_ascii=False).replace('</', '<\\/'), json.dumps(saved_live, ensure_ascii=False).replace('</', '<\\/'))

BODY = '''<body>
<div id="toast" role="status" aria-live="polite"></div>
<main class="app">
 <div class="topbar"><span class="snap" id="snap"></span><span class="win-tg" id="wintg" role="group" aria-label="Time window"></span><span class="tb-r"><span class="theme-tg" role="group" aria-label="Board look"><button type="button" data-theme="charcoal" aria-pressed="true"><i></i>Charcoal</button><button type="button" data-theme="paper" aria-pressed="false"><i></i>Paper</button></span><span>FNB Performance, %s</span></span></div>
 <nav class="rail" id="rail" role="tablist" aria-label="Cards" aria-orientation="vertical"></nav>
 <div><section class="ws" id="ws" role="tabpanel" aria-live="polite"></section><p class="demo-note" id="note"></p></div>
</main>
<div class="detail-scrim" id="detailScrim" hidden></div>
<aside class="detail" id="detailPanel" role="dialog" aria-modal="true" aria-labelledby="detailTitle" hidden><div class="detail-inner" id="detailBody" tabindex="-1"></div></aside>
''' % cp
def scoped(css, cls='paper'):
    """Prefix every rule of a theme sheet with html.<cls> so both looks live in one file."""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    out = []
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css):
        sel, body = m.group(1).strip(), m.group(2)
        if sel.startswith('@'):
            out.append(sel + '{' + body + '}')
            continue
        parts = []
        for x in (t.strip() for t in sel.split(',')):
            if x in (':root', 'html'):
                parts.append('html.' + cls)
            elif x.startswith('html'):
                parts.append('html.' + cls + x[4:])
            else:
                parts.append('html.' + cls + ' ' + x)
        out.append(','.join(parts) + '{' + body + '}')
    return '\n'.join(out) + '\n'


here = os.path.dirname(os.path.abspath(__file__))
font = base64.b64encode(open(os.path.join(here, 'fonts', 'bodoni-moda-latin-400-normal.woff2'), 'rb').read()).decode()
THEME_CSS = scoped(open(os.path.join(here, 'theme-paper.css'), encoding='utf-8').read()).replace('__BODONI__', font)
HEAD_JS = ("<script>try{var t=new URLSearchParams(location.search).get('theme')||localStorage.getItem('fnb-theme')||'%s';"
           "if(t==='paper')document.documentElement.classList.add('paper');}catch(e){}</script>\n") % ('paper' if theme == 'paper' else 'charcoal')
html = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<title>FNB Performance cards</title>\n' + HEAD_JS + '<style>\n' + css + CSS + THEME_CSS + '</style></head>\n' + BODY + '<script>\n' + engine + JS + '</script></body></html>\n')
open(out, 'w', encoding='utf-8').write(html)
print(len(html), len(saved.get('cards', [])))
