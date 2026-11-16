"""Builds 'FNB Performance cards.html' from the board engine (replica of public/app.js r3.30).

Usage: python tools/build_html.py <replica.html> <cards.json for the saved copy> <out.html> <checkpoint label>
The page draws the saved copy at once, then loads data/cards.json from GitHub and redraws if newer.

Layout (Checkpoint 9): card rail on the left; on the right a workspace for the selected card:
header, live strip, chart with next steps beside it, then up to three breakdowns.
The engine's chart, bars and Details dialog are reused unchanged.
"""
import json
import sys

rep, snap, out, cp = sys.argv[1:5]
src = open(rep, encoding='utf-8').read().split('\n')
css = '\n'.join(src[4:574])
engine = '\n'.join(src[587:680])
for a, b in [('>Day by day${', ">${esc(d.main.heading||'Day by day')}${"),
             ("${esc(where)}, last ${d.period} days", "${esc(where)}, ${esc(d.periodLabel||('last '+d.period+' days'))}"),
             ("const fmt=(n)=>n===null||n===undefined?'--':Number(n).toLocaleString('en-US',{maximumFractionDigits:0});",
              "const fmt=(n)=>n===null||n===undefined?'--':Number.isInteger(Number(n))?Number(n).toLocaleString('en-US'):Number(n).toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:2});"),
             ("const top=niceTop(Math.max(1,...all)*1.08);", "const top=unit==='points'?10:niceTop(Math.max(1,...all)*1.08);")]:
    assert engine.count(a) == 1, a
    engine = engine.replace(a, b)
saved = json.load(open(snap, encoding='utf-8'))

CSS = r'''
/* ===== Checkpoint 9 shell ===== */
html{zoom:.9}
body *{font-weight:400!important}
.ws-hero,.detail-value,.ask-stat strong{font-weight:250!important}
.stop-fnb-performance{stop-color:var(--u0)}
.app{position:relative;z-index:1;max-width:1840px;margin:0 auto;padding:22px 32px 28px;display:grid;grid-template-columns:292px minmax(0,1fr);gap:0 36px;align-items:start}
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
.rail-item span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rail-item strong{font-variant-numeric:tabular-nums;color:var(--ink)}
.rail-item em{font-style:normal;font-size:12px;text-align:right;font-variant-numeric:tabular-nums;color:var(--ink-4)}
.rail-item em.up{color:var(--good)}.rail-item em.down{color:var(--bad)}
/* workspace */
.ws{min-width:0;display:flex;flex-direction:column;gap:16px;animation:wsIn .45s var(--ease)}
@keyframes wsIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
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
.ws-main{display:grid;grid-template-columns:minmax(0,1.9fr) minmax(300px,1fr);gap:16px;align-items:stretch}
.ws .panel{padding:20px 22px}
.ph{font-size:12.5px;color:var(--ink-3);margin:0 0 14px;display:flex;justify-content:space-between;gap:12px}
.ph span{color:var(--ink-4)}
.ws-main>section{display:flex;flex-direction:column}
.ws-chart{flex:1;min-height:300px;height:auto}
.np{display:flex;flex-direction:column;gap:18px;max-height:520px;overflow:auto;scrollbar-width:thin}
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
/* heatmap */
.heat{display:flex;flex-direction:column;gap:4px}
.heat-row{appearance:none;border:0;background:transparent;display:grid;align-items:center;gap:6px;padding:0 8px;height:36px;border-radius:10px;text-align:left;color:var(--ink-2);font-size:13.5px;width:100%;transition:background .2s var(--ease)}
button.heat-row:hover{background:var(--surface-2);color:var(--ink)}
.heat-row.head{font-size:11.5px;color:var(--ink-4);height:24px}
.heat-row .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:flex;align-items:center;gap:8px}
.heat-row .nm small{color:var(--ink-4);font-size:11.5px}
.heat-row .tg{text-align:right;font-variant-numeric:tabular-nums;color:var(--ink-3);font-size:12.5px}
.heat-row.head span{text-align:center}.heat-row.head span:first-child{text-align:left}.heat-row.head span:last-child{text-align:right}
.cell{height:28px;border-radius:8px;display:grid;place-items:center;font-size:12.5px;font-variant-numeric:tabular-nums;color:var(--ink)}
.cell.good{background:color-mix(in srgb,var(--good) 30%,var(--surface))}.cell.warn{background:color-mix(in srgb,var(--warn) 26%,var(--surface))}.cell.bad{background:color-mix(in srgb,var(--bad) 28%,var(--surface))}
.cell.now.good{background:color-mix(in srgb,var(--good) 58%,var(--surface));color:#1d1e20}.cell.now.warn{background:color-mix(in srgb,var(--warn) 52%,var(--surface));color:#1d1e20}.cell.now.bad{background:color-mix(in srgb,var(--bad) 58%,var(--surface));color:#1d1e20}
.cell.none{background:var(--surface-2);color:var(--ink-4)}
/* popups (compact, sectioned) */
.detail.sheet{width:min(820px,calc(100vw - 48px));height:fit-content;max-height:min(860px,calc(100vh - 48px))}
.detail.sheet .detail-inner{overflow:auto;scrollbar-width:thin}
.pp-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;padding:20px 24px 14px;border-bottom:1px solid var(--line-soft);position:sticky;top:0;background:var(--canvas);z-index:2}
.pp-head .detail-title{font-size:24px}
.pp{padding:16px 24px 22px;display:flex;flex-direction:column;gap:12px}
.pill{display:inline-block;font-size:12.5px;padding:5px 12px;border-radius:999px;background:var(--surface-2);color:var(--ink-2)}
.pill.good{background:color-mix(in srgb,var(--good) 16%,var(--surface));color:var(--good)}
.pill.warn{background:color-mix(in srgb,var(--warn) 16%,var(--surface));color:var(--warn)}
.pill.bad{background:color-mix(in srgb,var(--bad) 16%,var(--surface));color:var(--bad)}
.box{background:var(--surface);border-radius:14px;padding:14px 16px;box-shadow:0 0 0 1px var(--line-soft) inset}
.box h4{font-size:13.5px;color:var(--ink);margin:0 0 10px;display:flex;justify-content:space-between;gap:12px}
.box h4 span{font-size:12px;color:var(--ink-4)}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px 18px}
.kv span{display:block;font-size:12px;color:var(--ink-3)}
.kv b{display:block;font-size:15px;color:var(--ink);margin-top:3px;font-variant-numeric:tabular-nums;overflow:hidden;text-overflow:ellipsis}
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
.heat-key{display:flex;gap:16px;align-items:center;font-size:11.5px;color:var(--ink-4);padding:10px 8px 0}
.heat-key i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.heat-key .good{background:color-mix(in srgb,var(--good) 58%,var(--surface))}.heat-key .warn{background:color-mix(in srgb,var(--warn) 52%,var(--surface))}.heat-key .bad{background:color-mix(in srgb,var(--bad) 58%,var(--surface))}
@media (max-width:1100px){.app{grid-template-columns:1fr;padding:16px}.rail{position:static;flex-direction:row;overflow-x:auto;gap:6px;padding-bottom:8px;scrollbar-width:none}.rail-group{display:none}.rail-item{display:flex;flex:none;gap:8px;white-space:nowrap;background:var(--surface);border-radius:999px;padding:9px 14px}.rail-item span{overflow:visible}.rail-item em{display:none}.ws-main{grid-template-columns:1fr}.strip{grid-template-columns:1fr 1fr}.strip>div+div{border-left:0}.bds{grid-template-columns:1fr}}
'''

JS = r'''
const SNAP_URL='https://raw.githubusercontent.com/RavenArtStudio/fnb-monitor/main/data/cards.json';
const SAVED=%s;
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
function drawRail(){let g='',h='';for(const d of CARDS){if(d.group!==g){g=d.group;h+=`<div class="rail-group">${GROUP_ICON[g]?`<svg viewBox="0 0 16 16" aria-hidden="true">${GROUP_ICON[g]}</svg>`:''}${esc(g)}</div>`;}const x=deltaOf(d);
 h+=`<button class="rail-item" role="tab" id="tab-${d.id}" data-card="${d.id}" aria-selected="${d.id===cur}" tabindex="${d.id===cur?0:-1}"><span>${esc(d.short)}</span><strong>${fmt(d.stats.total)}</strong><em class="${x.c}">${esc(x.t)}</em></button>`;}
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
 return [{label:d.main.tipLabel||'Previous period',value:fmt(s.previousTotal??pt)},
  {label:'Daily average',value:fmt(s.avgPerDay),note:`previous ${fmt(Math.round(pt/(prev.length||1)*10)/10)}`},
  vals[best]?{label:'Best day',value:fmt(vals[best]),note:ser[best]?sd(ser[best].date):''}:{label:'Best day',value:'--',note:'None yet'}];}
function stripHTML(d){const s=d.stats,ks=kpisOf(d);
 let chip='',tone='';if(s.deltaText){chip=s.deltaText;tone=s.deltaTone||'';}else if(s.change!=null){chip=`${s.change>0?'+':s.change<0?'−':''}${Math.abs(s.change)}%% on the previous ${d.period} days`;tone=s.change>0?'up':s.change<0?'down':'';}
 const unit=d.kind==='heatmap'?'of 10':esc(d.unit);
 const cap=d.periodLabel?esc(d.periodLabel):'';
 return `<div class="strip" style="--k:${ks.length}"><div><div class="hero-line"><span class="ws-hero">${fmt(s.total)}<small>${unit}</small></span>${chip?`<span class="chip ${tone}">${esc(chip)}</span>`:''}</div><div class="hero-cap">${cap}</div></div>${ks.map(k=>`<div class="kpi"><div class="k-l">${esc(k.label)}</div><div class="k-v">${esc(k.value)}</div>${k.note?`<div class="k-n ${k.tone||''}">${esc(k.note)}</div>`:''}</div>`).join('')}</div>`;}

/* ---- next steps + stand-outs ---- */
function nextHTML(d){const n=d.next||[];const pats=(d.patterns||[]).filter(p=>p.type!=='movement').slice(0,3);
 const steps=n.length?`<ol class="steps">${n.map(s=>`<li class="st"><span class="sd ${s.impact||''}"></span><div><p class="st-t">${esc(s.t)}</p>${s.why?`<p class="st-w">${esc(s.why)}</p>`:''}<span class="st-o"><span>${esc(OWNER[s.owner]||'')}</span>${s.gain?`<b>+${s.gain.toFixed(2)} points</b>`:''}<span>${s.impact==='high'?'High impact':s.impact==='med'?'Medium impact':'Low impact'}</span></span></div></li>`).join('')}</ol>`:'<p class="empty-note">Nothing to act on right now.</p>';
 const so=pats.length?`<div><h3 class="ph">What stands out</h3><div class="so">${pats.map(p=>`<div class="so-i ${esc(p.type)}"><span>${esc(p.title)}</span>${esc(p.evidence)}</div>`).join('')}</div></div>`:'';
 return `<div><h3 class="ph">Next steps<span>${n.length?'by impact':''}</span></h3>${steps}</div>${so}`;}

/* ---- breakdowns ---- */
function bdsHTML(d){const b=(d.breakdowns||[]).filter(x=>x.rows&&x.rows.length).slice(0,3);if(!b.length)return '';
 return `<div class="bds" style="--b:${Math.max(2,b.length)}">${b.map(x=>{const rows=x.rows.slice(0,5),max=Math.max(1,...rows.map(r=>r.value));
  return `<section class="panel"><h3 class="ph">${esc(x.title)}</h3><div class="hbars">${rows.map(r=>`<div class="hbar"><span title="${esc(r.label)}">${esc(r.label)}</span><div class="track"><div class="fill" data-w="${Math.max(1.5,100*r.value/max).toFixed(1)}"></div></div><strong>${fmt(r.value)}</strong></div>`).join('')}</div></section>`;}).join('')}</div>`;}

/* ---- columns chart (small daily counts) ---- */
function colChart(id,d){const frame=el(id),ser=Object.values(d.main.series)[0],cur=ser.map(p=>p?.value||0),prev=(d.main.previous||[]).map(p=>p?.value||0),dates=d.main.dates;
 const W=Math.max(280,frame.clientWidth||700),H=Math.max(180,frame.clientHeight||300),L=44,R=12,T=18,B=30,n=cur.length;
 const top=niceTop(Math.max(1,...cur,...prev)*1.15),y=v=>T+(1-v/top)*(H-T-B),slot=(W-L-R)/n,bw=Math.min(30,slot*.34);
 const grid=[0,.25,.5,.75,1].map(t=>`<line class="chart-grid" x1="${L}" x2="${W-R}" y1="${y(top*t).toFixed(1)}" y2="${y(top*t).toFixed(1)}"/><text class="chart-axis" x="${L-12}" y="${(y(top*t)+4).toFixed(1)}" text-anchor="end">${fmt(top*t)}</text>`).join('');
 let bars='';cur.forEach((v,i)=>{const cx=L+slot*(i+.5),h=Math.max(v?2:0,y(0)-y(v));
  bars+=`<g><title>${esc(nice(dates[i]))}: ${fmt(v)}${prev.length?`, ${esc(d.main.tipLabel||'previous')} ${fmt(prev[i])}`:''}</title><rect class="col-cur" x="${(cx-bw/2).toFixed(1)}" y="${(y(0)-h).toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" rx="4"/>${prev.length?`<line class="col-prev" x1="${(cx-bw/2-5).toFixed(1)}" x2="${(cx+bw/2+5).toFixed(1)}" y1="${y(prev[i]).toFixed(1)}" y2="${y(prev[i]).toFixed(1)}"/>`:''}${v?`<text class="col-val" x="${cx.toFixed(1)}" y="${(y(v)-7).toFixed(1)}" text-anchor="middle">${fmt(v)}</text>`:''}<text class="chart-axis" x="${cx.toFixed(1)}" y="${H-6}" text-anchor="middle">${esc(shortDate(dates[i]))}</text></g>`;});
 frame.innerHTML=`<svg role="img" aria-label="Daily ${esc(d.unit)} as columns, dashed marks are ${esc(d.main.tipLabel||'the previous period')}" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">${grid}${bars}</svg>`;}

/* ---- heatmap with in-place sub-metrics ---- */
function heatmap(id,d){const f=el(id),h=d.heat,n=h.cols.length;const cols=`minmax(0,1fr) repeat(${n},minmax(44px,92px)) 54px`;
 const one=(v)=>v===null||v===undefined?'--':Number(v).toFixed(1);
 const head=`<div class="heat-row head" style="grid-template-columns:${cols}"><span>Block, weight</span>${h.cols.map(c=>`<span>${esc(c)}</span>`).join('')}<span>Target</span></div>`;
 const rows=h.rows.map(r=>`<button class="heat-row" style="grid-template-columns:${cols}" data-sheet="${esc(r.id)}" aria-haspopup="dialog"><span class="nm">${esc(r.name)}<small>${r.weight}%%</small></span>${r.cells.map((v,i)=>`<span class="cell ${v===null||v===undefined?'none':r.bands[i]}${i===n-1?' now':''}" title="${esc(h.cols[i])}: ${one(v)}">${one(v)}</span>`).join('')}<span class="tg">${one(r.target)}</span></button>`).join('');
 const key=`<div class="heat-key"><span><i class="good"></i>On target</span><span><i class="warn"></i>Within 1.5</span><span><i class="bad"></i>Further below</span><span style="margin-left:auto">Select a block for its sub-metrics and next actions</span></div>`;
 f.innerHTML=`<div class="heat">${head}${rows}${key}</div>`;}

/* ---- block popup ---- */
const PILL=(tone,t)=>`<span class="pill ${tone}">${esc(t)}</span>`;
const KV=(items)=>`<div class="kv">${items.filter(Boolean).map(k=>`<div><span>${esc(k.label)}</span><b class="${k.tone||''}">${esc(k.value)}</b>${k.note?`<small>${esc(k.note)}</small>`:''}</div>`).join('')}</div>`;
const BOX=(title,inner,extra='')=>`<section class="box ${extra}"><h4>${title}</h4>${inner}</section>`;
const HEAD=(kicker,title)=>`<div class="pp-head"><div><div class="panel-kicker">${esc(kicker)}</div><h2 class="detail-title" id="detailTitle">${esc(title)}</h2></div>${CLOSE_BTN}</div>`;
const IDS={'Site health, Pages live':'pages','Site health, Broken links':'broken','Site health, Server response time':'response','Site health, Home page size':'weight','Site health, Pages with issues':'issues','Authority, Referring domains':'refdomains','Authority, Authority score':'authority','Google Search, Search impressions':'impressions','Google Search, Keywords on page one':'pageone','Enquiries, Profit Review requests':'leads','Enquiries, WhatsApp clicks':'whatsapp','Enquiries, Calculator uses':'tools'};
function sheetHTML(d,r){const one=(v)=>v===null||v===undefined?'--':Number(v).toFixed(1),now=r.cells.at(-1),gap=r.target-now,ok=gap<=0.05;
 const subs=[...r.subs].map(s=>({...s,gain:r.weight*s.weight*Math.max(0,r.target-s.score)/10000})).sort((a,b)=>b.gain-a.gain);
 const gainAll=subs.reduce((a,s)=>a+s.gain,0),live=subs.filter(s=>s.measured).length;
 const cards=(d.blocks?.[r.id]?.questions||[]).find(q=>q.id==='cards')?.answer?.items||[];
 const acts=subs.filter(s=>s.band!=='good'&&s.action);
 return HEAD(`Search visibility, ${d.heat.stage} stage`,r.name)+`<div class="pp">
  <div>${PILL(ok?'good':'bad',ok?`On target at ${one(now)}`:`${one(gap)} below the ${one(r.target)} target`)}</div>
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
 const pats=(d.patterns||[]).slice(0,4);
 const bds=(d.breakdowns||[]).filter(b=>b.rows&&b.rows.length);
 const srcRow=src?.rows?.[0]||[];
 return HEAD(`${d.group||''}, ${d.periodLabel||''}`,d.label)+`<div class="pp">
  <div>${pill}</div>
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
function chartHeading(d){if(d.kind==='heatmap')return `Blocks against the ${esc(d.heat.stage)} stage target<span>colour shows the latest snapshot against target</span>`;
 const p=d.main.previous;const label=d.main.tipLabel||'previous period';
 if(isCols(d))return `Day by day<span>${p?`dashed marks: ${esc(label.toLowerCase())}`:''}</span>`;
 return `${esc(d.main.heading||'Day by day')}<span>${p?`dashed line: ${esc((d.main.previousLabel||label).toLowerCase())}`:''}</span>`;}
function isCols(d){if(d.level||d.kind)return false;const v=[...Object.values(d.main.series)[0].map(p=>p?.value||0),...(d.main.previous||[]).map(p=>p?.value||0)];return Math.max(...v)<=10;}
function drawCard(animate=true){const d=BY[cur];if(!d)return;const ws=el('ws');
 ws.innerHTML=`<header class="ws-head"><div><h2>${esc(d.label)}</h2><p>${esc(d.sub||d.source)}</p></div><button class="link-quiet all" data-detail="card">All details</button></header>
 ${stripHTML(d)}
 <div class="ws-main"><section class="panel"><h3 class="ph">${chartHeading(d)}</h3><div id="analyticsChart" class="${d.kind==='heatmap'?'':'chart-frame ws-chart'}"></div></section><aside class="panel np">${nextHTML(d)}</aside></div>
 ${bdsHTML(d)}`;
 if(d.kind==='heatmap')heatmap('analyticsChart',d);
 else if(isCols(d))colChart('analyticsChart',d);
 else{const key=Object.keys(d.main.series)[0];lineChart('analyticsChart',{dates:d.main.dates,series:d.main.series,unit:d.unit,animate,ghost:d.main.previous?{[key]:d.main.previous}:null,ghostLabel:d.main.tipLabel||'Previous period'});}
 fillBars(ws);}
function setData(j,mode){META=j.meta||{};CARDS=j.cards||[];ORDER=CARDS.map(c=>c.id);BY=Object.fromEntries(CARDS.map(c=>[c.id,c]));
 const h=location.hash.slice(1);if(!ORDER.includes(cur))cur=ORDER.includes(h)?h:ORDER[0];
 el('snap').className='snap '+mode;el('snap').innerHTML=`<i></i>Snapshot ${esc(META.generated?when(META.generated):'not taken yet')}${mode==='saved'?', saved copy':''}`;
 const notes=(META.notes||[]).join(' ');el('note').textContent=(notes?notes+' ':'')+(mode==='saved'?'Showing the copy saved in this file; the latest snapshot could not be loaded.':'');
 drawRail();drawCard();}
function pick(id,focus){cur=id;history.replaceState(null,'','#'+id);document.querySelectorAll('.rail-item').forEach(b=>{const on=b.dataset.card===id;b.setAttribute('aria-selected',String(on));b.tabIndex=on?0:-1;if(on&&focus)b.focus();});drawCard();}
detailOpener=null;detailClosing=false;
function showDetail(d,metric,opener){detailOpener=opener;const panel=el('detailPanel'),scrim=el('detailScrim'),body=el('detailBody');
 state.detail={metric,data:d};panel.classList.add('sheet');body.innerHTML=detailHTML(d);
 scrim.hidden=false;panel.hidden=false;document.body.classList.add('detail-open');detailClosing=false;
 requestAnimationFrame(()=>{scrim.classList.add('on');panel.classList.add('on');});body.focus({preventScroll:true});}
function closeDetail(){const panel=el('detailPanel'),scrim=el('detailScrim');if(panel.hidden||detailClosing)return;detailClosing=true;
 panel.classList.remove('on');scrim.classList.remove('on');document.body.classList.remove('detail-open');
 setTimeout(()=>{if(!panel.classList.contains('on')){panel.hidden=true;scrim.hidden=true;panel.classList.remove('sheet');el('detailBody').innerHTML='';state.detail=null;}detailClosing=false;},reduceMotion?0:420);
 if(detailOpener&&document.contains(detailOpener))detailOpener.focus({preventScroll:true});}
document.addEventListener('click',e=>{
 const t=e.target.closest('[data-card],[data-sheet],[data-goto],[data-detail],[data-detail-close],[data-intent],[data-q],[data-raw],[data-copy-csv]');if(!t)return;
 if(t.dataset.card){pick(t.dataset.card);return;}
 if(t.dataset.sheet){openSheet(t.dataset.sheet,t);return;}
 if(t.dataset.goto){const id=t.dataset.goto;detailOpener=null;closeDetail();pick(id,true);return;}
 if(t.dataset.detail){showDetail(BY[cur],'card',t);return;}
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
setData(SAVED,'saved');
fetch(SNAP_URL+'?t='+Date.now(),{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(r.status)).then(j=>setData(j,'live')).catch(()=>{});
''' % json.dumps(saved, ensure_ascii=False).replace('</', '<\\/')

BODY = '''<body>
<div id="toast" role="status" aria-live="polite"></div>
<main class="app">
 <div class="topbar"><span class="snap" id="snap"></span><span>FNB Performance, %s</span></div>
 <nav class="rail" id="rail" role="tablist" aria-label="Cards" aria-orientation="vertical"></nav>
 <div><section class="ws" id="ws" role="tabpanel" aria-live="polite"></section><p class="demo-note" id="note"></p></div>
</main>
<div class="detail-scrim" id="detailScrim" hidden></div>
<aside class="detail" id="detailPanel" role="dialog" aria-modal="true" aria-labelledby="detailTitle" hidden><div class="detail-inner" id="detailBody" tabindex="-1"></div></aside>
''' % cp
html = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<title>FNB Performance cards</title>\n<style>\n' + css + CSS + '</style></head>\n' + BODY + '<script>\n' + engine + JS + '</script></body></html>\n')
open(out, 'w', encoding='utf-8').write(html)
print(len(html), len(saved.get('cards', [])))
