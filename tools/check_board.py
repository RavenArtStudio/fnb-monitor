"""Self-check of data/cards.json: every card and window must add up.

Usage: python tools/check_board.py [data/cards.json]   (prints problems; exit code 1 if any)
The snapshot runs it after building the cards and puts any problem into meta.notes, which the board shows.
"""
import datetime as dt
import json
import re
import sys

COUNT_TOL = 0.5


def vals(series):
    return [p.get("value") for p in series]


def check_bundle(cid, wkey, b, base, out):
    tag = f"{cid}/{wkey}"
    m, s = b.get("main") or {}, b.get("stats") or {}
    if not m or "series" not in m:
        return
    cur = vals(next(iter(m["series"].values())))
    dates = m.get("dates") or []
    if len(cur) != len(dates):
        out.append(f"{tag}: {len(cur)} values for {len(dates)} dates")
    if dates != sorted(dates):
        out.append(f"{tag}: dates out of order")
    if dates and "T" not in dates[0] and m.get("bucket") in ("day", None) and not b.get("level") and len(dates) > 1:
        ds = [dt.date.fromisoformat(x) for x in dates]
        gaps = [i for i in range(1, len(ds)) if (ds[i] - ds[i - 1]).days != 1]
        if gaps:
            out.append(f"{tag}: day keys not consecutive at {dates[gaps[0]]}")
    known = [v for v in cur if v is not None]
    tot = s.get("total")
    if b.get("level") or base.get("level"):
        if known and tot is not None and abs(tot - known[-1]) > COUNT_TOL:
            out.append(f"{tag}: headline {tot} is not the latest reading {known[-1]}")
        return
    if tot is not None and abs(tot - sum(known)) > COUNT_TOL:
        out.append(f"{tag}: headline {tot} but the chart adds up to {sum(known)}")
    prev = m.get("previous")
    if prev is not None:
        pv = [v for v in vals(prev) if v is not None]
        if len(prev) != len(dates):
            out.append(f"{tag}: previous period has {len(prev)} values for {len(dates)} dates")
        pt = s.get("previousTotal")
        if pt is not None and abs(pt - sum(pv)) > COUNT_TOL:
            out.append(f"{tag}: previous total {pt} but its line adds up to {sum(pv)}")
        ch = s.get("change")
        if ch is not None and pt:
            want = round(100 * (tot - pt) / pt)
            if abs(ch - want) > 1:
                out.append(f"{tag}: change {ch}% but {tot} against {pt} is {want}%")
        dtxt = s.get("deltaText") or ""
        mm = re.match(r"([+−-])(\d+)% on", dtxt)
        if mm and ch is not None and int(mm.group(2)) != abs(ch):
            out.append(f"{tag}: chip says {dtxt!r} but change is {ch}%")
    for bd in b.get("breakdowns") or []:
        rs = sum(r.get("value") or 0 for r in bd.get("rows", []))
        if tot and rs > tot * 1.02 + 1 and cid in ("leads", "whatsapp", "tools", "views", "impressions", "searchclicks"):
            out.append(f"{tag}: breakdown “{bd.get('title')}” adds up to {rs}, more than the headline {tot}")


def check_cube(c, out):
    h = c.get("heat") or {}
    rows = h.get("rows") or []
    if not rows:
        return
    total_w = sum(r.get("weight", 0) for r in rows)
    calc = 0
    on = 0
    for r in rows:
        subs = r.get("subs") or []
        if subs:
            v = sum(x["weight"] * x["score"] for x in subs) / sum(x["weight"] for x in subs)
            if abs(v - r["cells"][-1]) > 0.01:
                out.append(f"cube/{r['id']}: block shows {r['cells'][-1]} but its parts give {round(v, 2)}")
        calc += r["weight"] * r["cells"][-1] / 100
        on += r["cells"][-1] >= r["target"]
    if total_w != 100:
        out.append(f"cube: block weights add up to {total_w}, not 100")
    tot = (c.get("stats") or {}).get("total")
    if tot is not None and abs(round(calc, 2) - tot) > 0.01:
        out.append(f"cube: headline {tot} but the blocks give {round(calc, 2)}")
    for k in (c.get("kpis") or []):
        if k.get("label", "").startswith("Blocks on target"):
            mm = re.match(r"(\d+) of (\d+)", str(k.get("value", "")))
            if mm and int(mm.group(1)) != on:
                out.append(f"cube: strip says {k['value']} on target but {on} blocks are at or above target")


def check(d):
    out = []
    for c in d.get("cards", []):
        if c.get("kind") == "heatmap":
            check_cube(c, out)
            continue
        check_bundle(c["id"], "7d", c, c, out)
        for k, b in (c.get("w") or {}).items():
            check_bundle(c["id"], k, b, c, out)
        for k in c.get("wins") or []:
            if k != "7d" and k not in (c.get("w") or {}):
                out.append(f"{c['id']}: lists window {k} but has no data for it")
    return out


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "data/cards.json"
    probs = check(json.load(open(p, encoding="utf-8")))
    print("\n".join(probs) if probs else "No problems found.")
    sys.exit(1 if probs else 0)
