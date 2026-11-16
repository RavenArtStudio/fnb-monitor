"""Builds 'FNB Performance cards.html' from the board engine (replica of public/app.js r3.30).

Usage: python tools/build_html.py <replica.html> <cards.json for the saved copy> <out.html> <checkpoint label>
The page draws the saved copy at once, then loads data/cards.json from GitHub and redraws if newer.
"""
import json, sys
rep, snap, out, cp = sys.argv[1:5]
src = open(rep, encoding='utf-8').read().split('\n')
css = '\n'.join(src[4:574])
engine = '\n'.join(src[587:680])
for a, b in [('>Day by day${', ">${esc(d.main.heading||'Day by day')}${"),
             ("${esc(where)}, last ${d.period} days", "${esc(where)}, ${esc(d.periodLabel||('last '+d.period+' days'))}")]:
    assert a in engine, a
    engine = engine.replace(a, b)
saved = json.load(open(snap, encoding='utf-8'))

CSS = '''
/* Shell: card rail beside the unchanged card */
.stop-fnb-performance{stop-color:var(--u0)}
.demo-shell{max-width:1080px;padding:28px 24px 24px;display:grid;grid-template-columns:292px minmax(0,1fr);gap:8px 28px;align-items:start}
.demo-bar{grid-column:1/-1;margin-bottom:8px}
.rail{display:flex;flex-direction:column;min-width:0}
.rail-group{display:flex;align-items:center;gap:10px;font-size:11.5px;color:var(--ink-4);margin:8px 0 2px;padding:0 10px}
.rail-group:first-child{margin-top:0}
.rail-group::after{content:"";flex:1;height:1px;background:var(--line-soft)}
.rail-item{appearance:none;border:0;background:transparent;display:grid;grid-template-columns:minmax(0,1fr) auto 44px;gap:10px;align-items:baseline;text-align:left;padding:3.5px 10px;border-radius:10px;font-size:13px;color:var(--ink-2);transition:background .2s var(--ease),color .2s}
.rail-item:hover{background:var(--surface);color:var(--ink)}
.rail-item[aria-selected="true"]{background:var(--surface-2);color:var(--ink)}
.rail-item span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rail-item strong{font-weight:500;font-variant-numeric:tabular-nums;color:var(--ink)}
.rail-item em{font-style:normal;font-size:12px;text-align:right;font-variant-numeric:tabular-nums;color:var(--ink-3)}
.rail-item em.up{color:var(--good)}.rail-item em.down{color:var(--bad)}
.stage{min-width:0}
.stage .chart-frame{height:min(400px,calc(100vh - 300px));min-height:240px}
.demo-note{margin-top:12px}
.snap{display:inline-flex;align-items:center;gap:7px}
.snap i{width:6px;height:6px;border-radius:50%;background:var(--ink-4)}
.snap.live i{background:var(--good)}.snap.saved i{background:var(--warn)}
@media (max-width:900px){.demo-shell{grid-template-columns:1fr;padding:20px 16px 40px}.rail{flex-direction:row;overflow-x:auto;gap:6px;padding-bottom:6px;scrollbar-width:none}.rail-group{display:none}.rail-item{display:flex;flex:none;gap:8px;white-space:nowrap;background:var(--surface);border-radius:999px;padding:9px 14px;min-height:40px}.rail-item span{overflow:visible}.rail-item em{display:none}.stage .chart-frame{height:260px}}
'''
JS = r'''
const SNAP_URL='https://raw.githubusercontent.com/RavenArtStudio/fnb-monitor/main/data/cards.json';
const SAVED=%s;
let CARDS=[],ORDER=[],BY={},META={},cur=null;
const when=(iso)=>{const d=new Date(iso);return d.toLocaleDateString('en-US',{month:'short',day:'numeric'})+', '+d.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});};
function deltaOf(d){const s=d.stats;if(s.railText!==undefined)return {t:s.railText,c:s.railTone||''};if(d.level){const x=s.total-s.previousTotal;return {t:x===0?'level':(x>0?'+':'−')+fmt(Math.abs(x)),c:x>0?'up':x<0?'down':''};}
 if(s.change===null||s.change===undefined)return {t:'',c:''};return {t:s.change===0?'level':(s.change>0?'+':'−')+Math.abs(s.change)+'%%',c:s.change>0?'up':s.change<0?'down':''};}
function drawRail(){let g='',h='';for(const d of CARDS){if(d.group!==g){g=d.group;h+=`<div class="rail-group">${esc(g)}</div>`;}const x=deltaOf(d);
 h+=`<button class="rail-item" role="tab" id="tab-${d.id}" data-card="${d.id}" aria-selected="${d.id===cur}" tabindex="${d.id===cur?0:-1}"><span>${esc(d.short)}</span><strong>${fmt(d.stats.total)}</strong><em class="${x.c}">${esc(x.t)}</em></button>`;}
 el('rail').innerHTML=h;}
function drawCard(animate=true){const d=BY[cur];if(!d)return;el('cardTitle').textContent=d.label;el('cardSub').textContent=d.sub||d.source;
 const key=Object.keys(d.main.series)[0];
 lineChart('analyticsChart',{dates:d.main.dates,series:d.main.series,unit:d.unit,animate,ghost:d.main.previous?{[key]:d.main.previous}:null,ghostLabel:d.main.tipLabel||'Previous period'});}
function setData(j,mode){META=j.meta||{};CARDS=j.cards||[];ORDER=CARDS.map(c=>c.id);BY=Object.fromEntries(CARDS.map(c=>[c.id,c]));
 const h=location.hash.slice(1);if(!ORDER.includes(cur))cur=ORDER.includes(h)?h:ORDER[0];
 el('snap').className='snap '+mode;el('snap').innerHTML=`<i></i>Snapshot ${esc(META.generated?when(META.generated):'not taken yet')}${mode==='saved'?', saved copy':''}`;
 const notes=(META.notes||[]).join(' ');el('note').textContent=(notes?notes+' ':'')+(mode==='saved'?'Showing the copy saved in this file; the latest snapshot could not be loaded.':'');
 drawRail();drawCard();}
function pick(id,focus){cur=id;history.replaceState(null,'','#'+id);document.querySelectorAll('.rail-item').forEach(b=>{const on=b.dataset.card===id;b.setAttribute('aria-selected',String(on));b.tabIndex=on?0:-1;if(on&&focus)b.focus();if(on)b.scrollIntoView({block:'nearest',inline:'nearest'});});drawCard();}
detailOpener=null;detailClosing=false;
function openDetail(metric,opener){detailOpener=opener;const panel=el('detailPanel'),scrim=el('detailScrim'),body=el('detailBody'),d=BY[cur];
 state.detail={metric,intent:'status',open:d.questions?.find(q=>q.intent==='status')?.id||null,data:d};
 scrim.hidden=false;panel.hidden=false;document.body.classList.add('detail-open');detailClosing=false;
 requestAnimationFrame(()=>{scrim.classList.add('on');panel.classList.add('on');});body.focus({preventScroll:true});renderDetail();}
function closeDetail(){const panel=el('detailPanel'),scrim=el('detailScrim');if(panel.hidden||detailClosing)return;detailClosing=true;
 panel.classList.remove('on');scrim.classList.remove('on');document.body.classList.remove('detail-open');
 setTimeout(()=>{if(!panel.classList.contains('on')){panel.hidden=true;scrim.hidden=true;el('detailBody').innerHTML='';state.detail=null;}detailClosing=false;},reduceMotion?0:420);
 if(detailOpener&&document.contains(detailOpener))detailOpener.focus({preventScroll:true});}
document.addEventListener('click',e=>{
 const t=e.target.closest('[data-card],[data-detail],[data-detail-close],[data-intent],[data-q],[data-raw],[data-copy-csv]');if(!t)return;
 if(t.dataset.card){pick(t.dataset.card);return;}
 if(t.dataset.detail){openDetail(t.dataset.detail,t);return;}
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
<main class="demo-shell">
 <div class="demo-bar"><div class="panel-kicker"><span class="snap" id="snap"></span></div><div class="panel-kicker">FNB Performance, %s</div></div>
 <nav class="rail" id="rail" role="tablist" aria-label="Cards" aria-orientation="vertical"></nav>
 <div class="stage">
  <article class="panel" role="tabpanel"><div class="panel-head"><div><h2 id="cardTitle"></h2><p id="cardSub"></p></div><button class="link-quiet" data-detail="card">Details</button></div><div id="analyticsChart" class="chart-frame"></div></article>
  <p class="demo-note" id="note"></p>
 </div>
</main>
<div class="detail-scrim" id="detailScrim" hidden></div>
<aside class="detail" id="detailPanel" role="dialog" aria-modal="true" aria-labelledby="detailTitle" hidden><div class="detail-inner" id="detailBody" tabindex="-1"></div></aside>
''' % cp
html = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<title>FNB Performance cards</title>\n<style>\n' + css + CSS + '</style></head>\n' + BODY + '<script>\n' + engine + JS + '</script></body></html>\n')
open(out, 'w', encoding='utf-8').write(html)
print(len(html), len(saved.get('cards', [])))
