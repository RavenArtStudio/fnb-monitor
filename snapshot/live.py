"""Live feed for the short windows (30 min, 12 hours, 24 hours) of the Analytics cards.

Runs every 15 minutes (.github/workflows/live.yml). Reads Google Analytics Realtime, which covers
the last 30 minutes, and keeps its own minute-by-minute log so 12 and 24 hours (and the window
before each) can be built from it. Writes, into the folder given as the first argument:

  live-log.json   minutes seen in the last 49 hours: event counts and small breakdowns, plus coverage
  live.json       the window views the board merges into the Analytics cards

Both are published on the `live` branch as one overwritten commit, so the repo does not grow.
Realtime has no session, engagement, traffic-source, entry-page or host-name fields: sessions are
counted from session_start events, new visitors from first_visit, and Engaged sessions has no live view.
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import snapshot as S  # noqa: E402
from windows import WIN, wbundle, zkey, parse  # noqa: E402

UTC = dt.timezone.utc
KEEP_H = 49
EVENTS = ["session_start", "first_visit", "page_view", "generate_lead", "whatsapp_click", "tool_used"]


def realtime(sess, dims, metrics, flt=None):
    body = {"dimensions": [{"name": d} for d in dims], "metrics": [{"name": m} for m in metrics], "limit": 10000}
    if flt:
        body["dimensionFilter"] = flt
    r = sess.post(f"https://analyticsdata.googleapis.com/v1beta/properties/{S.GA_PROPERTY}:runRealtimeReport", json=body, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"GA realtime {r.status_code}: {r.text[:300]}")
    out = []
    for row in r.json().get("rows", []):
        out.append(([v["value"] for v in row.get("dimensionValues", [])], [float(v["value"]) for v in row["metricValues"]]))
    return out


def title(t):
    t = (t or "").strip()
    for sep in (" | ", " – ", " — "):
        if sep in t:
            t = t.split(sep)[0]
    return S.tidy(t) if t else "Not recorded"


def inlist(names):
    return {"filter": {"fieldName": "eventName", "inListFilter": {"values": names}}}


def read_minutes(sess, now):
    """Realtime rows -> {minute key: record}. minutesAgo 00 is the current minute, still filling."""
    rec = {}
    def slot(ago):
        k = zkey(now - dt.timedelta(minutes=int(ago)))
        return rec.setdefault(k, {"e": {}, "sc": {}, "sd": {}, "nc": {}, "pp": {}, "ep": {}})
    add = lambda d, k, v: d.__setitem__(k, d.get(k, 0) + int(v))
    for (ago, name), (n,) in realtime(sess, ["minutesAgo", "eventName"], ["eventCount"]):
        add(slot(ago)["e"], name, n)
    for (ago, name, cty, dev), (n,) in realtime(sess, ["minutesAgo", "eventName", "country", "deviceCategory"], ["eventCount"], inlist(["session_start", "first_visit"])):
        r = slot(ago)
        if name == "session_start":
            add(r["sc"], S.tidy(cty), n)
            add(r["sd"], S.tidy(dev), n)
        else:
            add(r["nc"], S.tidy(cty), n)
    for (ago, name, scr), (n,) in realtime(sess, ["minutesAgo", "eventName", "unifiedScreenName"], ["eventCount"], inlist(["page_view", "generate_lead", "whatsapp_click", "tool_used"])):
        r = slot(ago)
        if name == "page_view":
            add(r["pp"], title(scr), n)
        else:
            add(r["ep"].setdefault(name, {}), title(scr), n)
    au = realtime(sess, [], ["activeUsers"])
    active = int(au[0][1][0]) if au else 0
    return {k: {a: b for a, b in v.items() if b} for k, v in rec.items()}, active


def merge_cover(cover, lo, hi):
    rs = sorted([tuple(x) for x in cover] + [(lo, hi)])
    out = []
    for a, b in rs:
        if out and parse(a) <= parse(out[-1][1]) + dt.timedelta(minutes=1):
            if parse(b) > parse(out[-1][1]):
                out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return [list(x) for x in out]


def covered(cover):
    spans = [(parse(a), parse(b)) for a, b in cover]
    return lambda t: any(a <= t <= b for a, b in spans)


def run(sess, folder, now=None):
    folder = Path(folder)
    now = (now or dt.datetime.now(UTC)).replace(second=0, microsecond=0)
    lp = folder / "live-log.json"
    log = json.loads(lp.read_text()) if lp.exists() and lp.read_text().strip() not in ("", "{}") else {"v": 1, "cover": [], "m": {}, "au": []}
    recs, active = read_minutes(sess, now)
    lo, hi = zkey(now - dt.timedelta(minutes=29)), zkey(now)
    for i in range(30):                                   # a later reading of a minute replaces the earlier one
        log["m"].pop(zkey(now - dt.timedelta(minutes=i)), None)
    log["m"].update({k: v for k, v in recs.items() if v})
    log["cover"] = merge_cover(log["cover"], lo, hi)
    log["au"] = (log.get("au") or []) + [[zkey(now), active]]
    cut = now - dt.timedelta(hours=KEEP_H)
    log["m"] = {k: v for k, v in log["m"].items() if parse(k) > cut}
    log["cover"] = [[max(a, zkey(cut)), b] for a, b in log["cover"] if parse(b) > cut]
    log["au"] = [x for x in log["au"] if parse(x[0]) > cut]
    lp.write_text(json.dumps(log, separators=(",", ":")))
    (folder / "live.json").write_text(json.dumps(build(log, now, active), ensure_ascii=False, separators=(",", ":")))


def build(log, now, active):
    cov = covered(log["cover"])
    M = log["m"]
    minute = lambda t: M.get(zkey(t), {})

    def buckets(wkey):
        """[(start, [minute datetimes])] for the window and the one before it."""
        if wkey == "30m":
            cur = [(now - dt.timedelta(minutes=29 - i), [now - dt.timedelta(minutes=29 - i)]) for i in range(30)]
            prev = [(t - dt.timedelta(minutes=30), [m - dt.timedelta(minutes=30) for m in ms]) for t, ms in cur]
            return cur, prev, 1
        n = WIN[wkey]["n"]
        cur = []
        for i in range(n):
            end = now - dt.timedelta(hours=n - 1 - i)
            ms = [end - dt.timedelta(minutes=59 - j) for j in range(60)]
            cur.append((ms[0], ms))
        prev = [(t - dt.timedelta(hours=n), [m - dt.timedelta(hours=n) for m in ms]) for t, ms in cur]
        return cur, prev, 60

    def values(bs, get):
        out, part = [], []
        for i, (t, ms) in enumerate(bs):
            seen = [m for m in ms if cov(m)]
            if not seen:
                out.append(None)
                continue
            out.append(sum(get(minute(m)) for m in seen))
            if len(seen) < 0.9 * len(ms):
                part.append(i)
        return out, part

    def agg(bs, pick):
        tot = {}
        for _, ms in bs:
            for m in ms:
                if cov(m):
                    for k, v in pick(minute(m)).items():
                        tot[k] = tot.get(k, 0) + v
        items = sorted(tot.items(), key=lambda x: -x[1])
        if len(items) > 6:
            items = items[:5] + [("Other", sum(v for _, v in items[5:]))]
        return items

    ev = lambda name: (lambda r: r.get("e", {}).get(name, 0))
    epage = lambda name: (lambda r: r.get("ep", {}).get(name, {}))
    feed = ("Google Analytics Realtime: events of the last 30 minutes, saved every 15 minutes. "
            "Longer live windows are built from those saved minutes.")
    nohost = "The live feed has no traffic source, entry page or host name, so visits from development hosts count here too."
    cards = {}
    for wkey in ("30m", "12h", "24h"):
        cur_b, prev_b, step = buckets(wkey)
        keys = [zkey(t) for t, _ in cur_b]
        early = zkey(now) if wkey == "30m" else None
        common = dict(keys=keys, step_min=step, launch=S.LAUNCH, sub_source=f"{S.GA}, live", early_from=early)
        defs = {
            "sessions": ("Website sessions", "sessions", "session_start", "eventName = session_start, eventCount, country, deviceCategory, unifiedScreenName",
                         [("Country", agg(cur_b, lambda r: r.get("sc", {})), "Which countries are they in?", "Country"),
                          ("Device", agg(cur_b, lambda r: r.get("sd", {})), "What are they browsing on?", "Device"),
                          ("Pages viewed", agg(cur_b, lambda r: r.get("pp", {})), "Which pages are they reading?", "Page title")],
                         "Sessions started, counted from session_start events in Google Analytics' live feed.",
                         ["The 7-day view uses Google's processed sessions, so the two can differ slightly.", nohost]),
            "newvisitors": ("New visitors", "visitors", "first_visit", "eventName = first_visit, eventCount, country",
                            [("Country of new visitors", agg(cur_b, lambda r: r.get("nc", {})), "Where are new visitors from?", "Country")],
                            "First visits, counted from first_visit events in Google Analytics' live feed.",
                            ["Team members count as new on each new device until internal traffic is filtered.", nohost]),
            "views": ("Page views", "views", "page_view", "eventName = page_view, eventCount, unifiedScreenName",
                      [("By page", agg(cur_b, lambda r: r.get("pp", {})), "Which pages are viewed most?", "Page title")],
                      "Every page load, counted from page_view events in Google Analytics' live feed.", [nohost]),
            "leads": ("Profit Review requests", "requests", "generate_lead", "eventName = generate_lead, eventCount, unifiedScreenName",
                      [("Page the request was sent from", agg(cur_b, epage("generate_lead")), "Which page were requests sent from?", "Page title")],
                      "Count of the generate_lead event the site sends when the Profit Review form is sent successfully.",
                      ["Requests made by phone, email or WhatsApp are not counted here.", nohost]),
            "whatsapp": ("WhatsApp clicks", "clicks", "whatsapp_click", "eventName = whatsapp_click, eventCount, unifiedScreenName",
                         [("Page the click came from", agg(cur_b, epage("whatsapp_click")), "Which pages produce WhatsApp clicks?", "Page title")],
                         "Count of the whatsapp_click event the site sends.", ["A click opens WhatsApp; it does not prove a message was sent.", nohost]),
            "tools": ("Calculator uses", "uses", "tool_used", "eventName = tool_used, eventCount, unifiedScreenName",
                      [("By calculator page", agg(cur_b, epage("tool_used")), "Which calculators are used most?", "Page title")],
                      "Count of the tool_used event the site sends when a calculator is used.", [nohost]),
        }
        for cid, (label, unit, name, fields, bds, how, cav) in defs.items():
            cur, part = values(cur_b, ev(name))
            prev, _ = values(prev_b, ev(name))
            if all(v is None for v in prev):
                prev = None
            notes = []
            if cid == "sessions" and wkey == "30m":
                notes.append({"type": "movement", "title": f"{active} {'person' if active == 1 else 'people'} active in the last 30 min",
                              "evidence": "Unique users Google Analytics saw on the site in the last 30 minutes."})
            if wkey == "30m":
                notes.append({"type": "caution", "title": "The latest minute is still filling",
                              "evidence": "Google adds events for the current minute as they arrive."})
            b = wbundle(wkey, label=label, unit=unit, source=S.GA, fields=fields, cur=cur, prev=prev,
                        breakdowns=[x for x in bds if x[1]], how=how, caveats=[feed] + cav + [S.CONSENT], notes=notes, **common)
            if part:
                b["main"]["partial"] = part
                b["patterns"].append({"type": "caution", "title": f"{len(part)} of {len(cur)} {WIN[wkey]['bucket']}s partly recorded",
                                      "evidence": "The live feed missed some minutes in those buckets; they show lighter in the chart."})
            if prev is None:
                b["stats"].update({"previousTotal": None, "change": None,
                                   "deltaText": "No earlier live record to compare with yet", "deltaTone": "", "railText": "", "railTone": ""})
            c = cards.setdefault(cid, {"wins": ["30m", "12h", "24h"], "w": {}})
            c["w"][wkey] = b
    day_cov = sum(1 for i in range(24 * 60) if cov(now - dt.timedelta(minutes=i))) / (24 * 60)
    return {"meta": {"generated": now.isoformat(timespec="minutes"), "minute": zkey(now), "active": active,
                     "cover24h": round(day_cov, 3)}, "cards": cards}


if __name__ == "__main__":
    sess = S.google_session()
    if not sess:
        sys.exit("GOOGLE_SA_KEY not set")
    run(sess, sys.argv[1] if len(sys.argv) > 1 else ".")
