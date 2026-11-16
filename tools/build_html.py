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
button.heat-row:hover,button.heat-row[aria-expanded="true"]{background:var(--surface-2);color:var(--ink)}
.heat-row.head{font-size:11.5px;color:var(--ink-4);height:24px}
.heat-row .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:flex;align-items:center;gap:8px}
.heat-row .nm i{font-style:normal;color:var(--ink-4);font-size:11px;transition:transform .25s var(--ease);display:inline-block;width:8px}
.heat-row[aria-expanded="true"] .nm i{transform:rotate(90deg)}
.heat-row .nm small{color:var(--ink-4);font-size:11.5px}
.heat-row .tg{text-align:right;font-variant-numeric:tabular-nums;color:var(--ink-3);font-size:12.5px}
.heat-row.head span{text-align:center}.heat-row.head span:first-child{text-align:left}.heat-row.head span:last-child{text-align:right}
.cell{height:28px;border-radius:8px;display:grid;place-items:center;font-size:12.5px;font-variant-numeric:tabular-nums;color:var(--ink)}
.cell.good{background:color-mix(in srgb,var(--good) 30%,var(--surface))}.cell.warn{background:color-mix(in srgb,var(--warn) 26%,var(--surface))}.cell.bad{background:color-mix(in srgb,var(--bad) 28%,var(--surface))}
.cell.now.good{background:color-mix(in srgb,var(--good) 58%,var(--surface));color:#1d1e20}.cell.now.warn{background:color-mix(in srgb,var(--warn) 52%,var(--surface));color:#1d1e20}.cell.now.bad{background:color-mix(in srgb,var(--bad) 58%,var(--surface));color:#1d1e20}
.cell.none{background:var(--surface-2);color:var(--ink-4)}
.subs{display:flex;flex-direction:column;gap:2px;padding:4px 0 10px;animation:wsIn .35s var(--ease)}
.sub{display:grid;align-items:center;gap:2px 6px;padding:6px 8px;font-size:12.5px;color:var(--ink-3);border-radius:8px}
.sub:hover{background:#ffffff05}
.sub .sx{grid-column:1/-1;padding-left:16px;font-size:12px;color:var(--ink-4);line-height:1.5}
.sub .sa{display:block;color:var(--ink-2);margin-top:2px}
.sub .sa i{font-style:normal;color:var(--ink-4);margin-left:8px;font-size:11.5px}
.sub .sn{padding-left:16px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink-2)}
.sub .sn em{font-style:normal;font-size:11px;color:var(--ink-4);margin-left:8px}
.sbar{display:grid;grid-template-columns:1fr 3em;gap:10px;align-items:center}
.sbar .tr{height:6px;border-radius:99px;background:var(--surface-3);overflow:hidden}
.sbar .fl{height:100%;border-radius:99px}
.fl.good{background:var(--good)}.fl.warn{background:var(--warn)}.fl.bad{background:var(--bad)}
.sbar b{text-align:right;color:var(--ink-2);font-variant-numeric:tabular-nums}
.sub .tg{text-align:right;color:var(--ink-4);font-size:11.5px}
.subs .more{align-self:flex-start;margin:4px 0 0 32px}
.heat-key{display:flex;gap:16px;align-items:center;font-size:11.5px;color:var(--ink-4);padding:10px 8px 0}
.heat-key i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.heat-key .good{background:color-mix(in srgb,var(--good) 58%,var(--surface))}.heat-key .warn{background:color-mix(in srgb,var(--warn) 52%,var(--surface))}.heat-key .bad{background:color-mix(in srgb,var(--bad) 58%,var(--surface))}
@media (max-width:1100px){.app{grid-template-columns:1fr;padding:16px}.rail{position:static;flex-direction:row;overflow-x:auto;gap:6px;padding-bottom:8px;scrollbar-width:none}.rail-group{display:none}.rail-item{display:flex;flex:none;gap:8px;white-space:nowrap;background:var(--surface);border-radius:999px;padding:9px 14px}.rail-item span{overflow:visible}.rail-item em{display:none}.ws-main{grid-template-columns:1fr}.strip{grid-template-columns:1fr 1fr}.strip>div+div{border-left:0}.bds{grid-template-columns:1fr}}
'''

JS = r'''
const SNAP_URL='https://raw.githubusercontent.com/RavenArtStudio/fnb-monitor/main/data/cards.json';
const SAVED=%s;
let CARDS=[],ORDER=[],BY={},META={},cur=null,OPEN=new Set();
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
 const rows=h.rows.map(r=>{const open=OPEN.has(r.id);
  const gc=`minmax(0,1fr) ${n>1?`repeat(${n},minmax(44px,92px))`:'minmax(44px,92px)'} 54px`;
  const subs=open?`<div class="subs">${r.subs.map(s=>{const ev=s.measured?(s.evidence||''):`Audit score, Nov 13${s.evidence?': '+s.evidence:''}`;const moved=s.measured&&s.audit!=null&&Math.abs(s.score-s.audit)>=0.05?` Audit ${one(s.audit)}.`:'';
   return `<div class="sub" style="grid-template-columns:${gc}"><span class="sn">${esc(s.name)}<em>${s.measured?'live':'audit'}</em></span><span class="sbar" style="grid-column:span ${n}"><span class="tr"><span class="fl ${s.band}" style="display:block;width:${Math.max(2,s.score*10)}%%"></span></span><b>${one(s.score)}</b></span><span class="tg">${s.weight}%%</span><span class="sx">${esc(ev+moved)}${s.band!=='good'&&s.action?`<span class="sa">Next: ${esc(s.action)}<i>${esc(OWNER[s.owner]||'')}</i></span>`:''}</span></div>`;}).join('')}</div>`:'';
  return `<button class="heat-row" style="grid-template-columns:${cols}" data-expand="${esc(r.id)}" aria-expanded="${open}"><span class="nm"><i>›</i>${esc(r.name)}<small>${r.weight}%%</small></span>${r.cells.map((v,i)=>`<span class="cell ${v===null||v===undefined?'none':r.bands[i]}${i===n-1?' now':''}" title="${esc(h.cols[i])}: ${one(v)}">${one(v)}</span>`).join('')}<span class="tg">${one(r.target)}</span></button>${subs}`;}).join('');
 const key=`<div class="heat-key"><span><i class="good"></i>On target</span><span><i class="warn"></i>Within 1.5</span><span><i class="bad"></i>Further below</span><span style="margin-left:auto">Select a block for its sub-metrics, evidence and next action</span></div>`;
 f.innerHTML=`<div class="heat">${head}${rows}${key}</div>`;}

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
 state.detail={metric,intent:'status',open:d.questions?.find(q=>q.intent==='status')?.id||null,data:d};
 scrim.hidden=false;panel.hidden=false;document.body.classList.add('detail-open');detailClosing=false;
 requestAnimationFrame(()=>{scrim.classList.add('on');panel.classList.add('on');});body.focus({preventScroll:true});renderDetail();}
function closeDetail(){const panel=el('detailPanel'),scrim=el('detailScrim');if(panel.hidden||detailClosing)return;detailClosing=true;
 panel.classList.remove('on');scrim.classList.remove('on');document.body.classList.remove('detail-open');
 setTimeout(()=>{if(!panel.classList.contains('on')){panel.hidden=true;scrim.hidden=true;el('detailBody').innerHTML='';state.detail=null;}detailClosing=false;},reduceMotion?0:420);
 if(detailOpener&&document.contains(detailOpener))detailOpener.focus({preventScroll:true});}
document.addEventListener('click',e=>{
 const t=e.target.closest('[data-card],[data-expand],[data-block],[data-detail],[data-detail-close],[data-intent],[data-q],[data-raw],[data-copy-csv]');if(!t)return;
 if(t.dataset.card){pick(t.dataset.card);return;}
 if(t.dataset.expand){const id=t.dataset.expand;OPEN.has(id)?OPEN.delete(id):OPEN.add(id);heatmap('analyticsChart',BY[cur]);document.querySelector(`[data-expand="${id}"]`)?.focus({preventScroll:true});return;}
 if(t.dataset.block){const b=BY[cur]?.blocks?.[t.dataset.block];if(b)showDetail(b,t.dataset.block,t);return;}
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
