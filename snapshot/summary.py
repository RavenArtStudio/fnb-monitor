"""Small per-site summary for Babar's workspace home card (Checkpoint 31).

Written next to cards.json on every snapshot: data/summary.json and data/sites/<id>/summary.json.
About 1 KB, so the workspace can show every site's headline without loading the full board files.

  python snapshot/summary.py            # rebuild every site's summary from its saved cards.json
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = ('leads', 'sessions', 'impressions')


def site_name(data_dir):
    data_dir = Path(data_dir).resolve()
    for f in sorted((ROOT / 'sites').glob('*.json')):
        cfg = json.loads(f.read_text(encoding='utf-8'))
        if (ROOT / cfg.get('data_dir', 'data')).resolve() == data_dir:
            return f.stem, cfg.get('name', f.stem), (cfg.get('hosts') or [None])[0]
    return data_dir.name, data_dir.name, None


def build(out, data_dir):
    cards = {c.get('id'): c for c in out.get('cards', [])}
    sid, name, host = site_name(data_dir)
    s = {'site': sid, 'name': name, 'host': host, 'generated': (out.get('meta') or {}).get('generated')}
    cube = cards.get('cube') or {}
    st = cube.get('stats') or {}
    heat = cube.get('heat') or {}
    trend = []
    for i in range(len(heat.get('cols') or [])):
        num = den = 0.0
        for row in heat.get('rows') or []:
            cells = row.get('cells') or []
            v = cells[i] if i < len(cells) else None
            if isinstance(v, (int, float)) and isinstance(row.get('weight'), (int, float)):
                num += row['weight'] * v
                den += row['weight']
        trend.append(round(num / den, 2) if den else None)
    target = next((k.get('value') for k in cube.get('kpis') or [] if k.get('label') == 'Stage target'), None)
    s['score'] = {'value': st.get('total'), 'delta': st.get('railText'), 'tone': st.get('deltaTone'),
                  'deltaText': st.get('deltaText'), 'stage': cube.get('sub'), 'target': target,
                  'trend': trend, 'trendLabels': heat.get('cols') or []}
    s['metrics'] = []
    for key in METRICS:
        c = cards.get(key)
        if not c or not c.get('available', True):
            continue
        cs = c.get('stats') or {}
        s['metrics'].append({'id': key, 'label': c.get('short') or c.get('label'), 'total': cs.get('total'),
                             'change': cs.get('change'), 'railText': cs.get('railText'), 'tone': cs.get('railTone') or cs.get('deltaTone'),
                             'period': c.get('periodLabel')})
    return s


def write(data_dir, out):
    data_dir = Path(data_dir)
    (data_dir / 'summary.json').write_text(json.dumps(build(out, data_dir), ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


if __name__ == '__main__':
    for f in sorted((ROOT / 'sites').glob('*.json')):
        dd = ROOT / json.loads(f.read_text(encoding='utf-8')).get('data_dir', 'data')
        if (dd / 'cards.json').exists():
            write(dd, json.loads((dd / 'cards.json').read_text(encoding='utf-8')))
            print(dd / 'summary.json')
