"""Time windows for the board's central toggle (Checkpoint 27).

Windows: 30m, 12h, 24h, 7d, 30d, all. Each window ends at its latest complete bucket
(minute, hour or day) and is compared with the window of the same length just before it.
'all' runs from the launch and has no comparison.

Times inside card text are written as markers the board turns into the viewer's local time:
  @@2026-11-18T20:15Z@@    -> 01:45
  @@d:2026-11-18T20:15Z@@  -> Nov 19, 01:45
"""
import datetime as dt
from siteconf import CFG as _SITE_CFG  # noqa: E402
SITE_NAME = _SITE_CFG["name"]

ORDER = ["30m", "12h", "24h", "7d", "30d", "all"]
WIN = {
    "30m": {"n": 30, "bucket": "minute", "span": "30 min", "every": "per minute", "Bucket": "Minute"},
    "12h": {"n": 12, "bucket": "hour", "span": "12 hours", "every": "per hour", "Bucket": "Hour"},
    "24h": {"n": 24, "bucket": "hour", "span": "24 hours", "every": "per hour", "Bucket": "Hour"},
    "7d": {"n": 7, "bucket": "day", "span": "7 days", "every": "per day", "Bucket": "Day"},
    "30d": {"n": 30, "bucket": "day", "span": "30 days", "every": "per day", "Bucket": "Day"},
    "all": {"n": None, "bucket": "day", "span": "since launch", "every": "per day", "Bucket": "Day"},
}

f = lambda n: f"{n:,}" if isinstance(n, int) else (f"{n:,.1f}" if isinstance(n, float) else str(n))
short = lambda d: f"{d.strftime('%b')} {d.day}"
UTC = dt.timezone.utc


def zkey(t):
    """UTC datetime -> '2026-11-18T20:15Z'."""
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ")


def parse(k):
    if "T" in k:
        return dt.datetime.strptime(k, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)
    return dt.date.fromisoformat(k)


def klab(k, with_day=False):
    """Label for a bucket key: a date gives 'Nov 17'; a time gives a marker the board localises."""
    if "T" in k:
        return f"@@{'d:' if with_day else ''}{k}@@"
    return short(dt.date.fromisoformat(k))


def span_label(keys, wkey, step_min=None):
    """'Nov 11 to Nov 17', or local times for the short windows."""
    if not keys:
        return ""
    if "T" not in keys[0]:
        return f"{klab(keys[0])} to {klab(keys[-1])}"
    end = zkey(parse(keys[-1]) + dt.timedelta(minutes=step_min or 1))
    return f"{klab(keys[0], wkey != '30m')} to {klab(end, wkey != '30m')}"


def pct(a, b):
    return round(100 * (a - b) / b) if b else None


def wbundle(wkey, *, label, unit, source, fields, keys, cur, prev, breakdowns, how, caveats,
            sub_source=None, nxt_q=None, old_prev=False, old_part=False, launch=None, step_min=None,
            notes=None, early_from=None, extra=None):
    """One window's view of a count card (the same fields the board reads from a 7-day card).

    keys: bucket keys, oldest first; cur: values (None = not recorded); prev: values of the
    previous window aligned to keys, or None for 'all'. breakdowns: [(title, rows, question, column)].
    """
    W = WIN[wkey]
    known = [v for v in cur if v is not None]
    tot = int(sum(known)) if known else 0
    pk = [v for v in (prev or []) if v is not None]
    ptot = int(sum(pk)) if prev is not None else None
    ch = pct(tot, ptot) if ptot is not None else None
    per = round(tot / len(known), 1) if known else 0
    missing = len(cur) - len(known)
    stats = {"total": tot, "previousTotal": ptot, "change": ch, "avgPerDay": per,
             "avgLabel": f"Average {W['every']}", "bestLabel": f"Busiest {W['bucket']}"}
    if wkey == "all":
        n_days = len(keys)
        stats["deltaText"] = f"since {short(launch)}, {n_days} day{'s' if n_days != 1 else ''}"
        stats["deltaTone"], stats["railText"], stats["railTone"] = "", "", ""
    elif ptot == 0 and tot > 0:
        stats["deltaText"], stats["deltaTone"] = f"{f(tot)} against none in the previous {W['span']}", "up"
        stats["railText"], stats["railTone"] = "new", "up"
    elif ptot == 0 and tot == 0:
        stats["deltaText"], stats["deltaTone"] = f"None in the previous {W['span']} either", ""
        stats["railText"], stats["railTone"] = "level", ""
    elif ch is not None:
        stats["deltaText"] = ("Level with" if ch == 0 else f"{'+' if ch > 0 else '−'}{abs(ch)}% on") + f" the previous {W['span']}"
        stats["deltaTone"] = "up" if ch > 0 else "down" if ch < 0 else ""
    pats = []
    if wkey != "all" and ch is not None:
        pats.append({"type": "movement",
                     "title": f"{label} {'up' if ch > 0 else 'down' if ch < 0 else 'level'}{'' if ch == 0 else ' ' + str(abs(ch)) + '%'} on the previous {W['span']}",
                     "evidence": f"{f(tot)} {unit} against {f(ptot)} in the {W['span']} before."})
    elif wkey == "all":
        pats.append({"type": "movement", "title": f"{f(tot)} {unit} since the launch",
                     "evidence": f"{per} {W['every']} over {len(keys)} days from {short(launch)}."})
    if known and max(known) > 1:
        i = cur.index(max(known))
        pats.append({"type": "peak", "title": f"Busiest {W['bucket']} was {klab(keys[i], W['bucket'] == 'hour')}",
                     "evidence": f"{f(cur[i])} {unit}, against an average of {per} {W['every']}."})
    if missing:
        pats.append({"type": "caution", "title": f"{missing} of {len(cur)} {W['bucket']}s not recorded",
                     "evidence": "The live feed missed those runs, so the total is a floor; gaps show as breaks in the chart."})
    if old_prev:
        pats.append({"type": "caution", "title": "Compared with the old site",
                     "evidence": f"The new site went live on {short(launch)}. The previous {W['span']} are the old site"
                                 + (", and so are the days before launch in this window." if old_part else ".")})
    for n in notes or []:
        pats.append(n)
    for b in breakdowns:
        s = sum(r[1] for r in b[1])
        if s and len(b[1]) > 1 and b[1][0][1] / s >= .45:
            pats.append({"type": "concentration", "title": f"{b[1][0][0]} accounts for {round(100 * b[1][0][1] / s)}%",
                         "evidence": f"{f(b[1][0][1])} of {f(s)} under “{b[0]}”."})
            break
    span = span_label(keys, wkey, step_min)
    order = sorted([j for j in range(len(cur)) if cur[j] is not None], key=lambda j: -cur[j])
    q = [{"intent": "status", "id": "total", "text": "What is the reading?",
          "answer": {"type": "stat", "value": f(tot), "label": f"{label}, {'last ' + W['span'] if wkey != 'all' else W['span']}",
                     "sub": stats.get("deltaText", "")}}]
    if prev is not None:
        q.append({"intent": "change", "id": "compare", "text": "How does this compare with before?",
                  "answer": {"type": "table", "columns": ["Period", label],
                             "rows": [[f"Latest {W['span']}", f(tot)], [f"Previous {W['span']}", f(ptot)],
                                      ["Change", ("+" if (ch or 0) > 0 else "") + (f"{ch}%" if ch is not None else f(tot - ptot))]], "note": ""}})
    if any(known):
        q.append({"intent": "change", "id": "days", "text": f"Which {W['bucket']}s were busiest and quietest?",
                  "answer": {"type": "table", "columns": [W["Bucket"], "Value"],
                             "rows": [[klab(keys[j], W['bucket'] == 'hour') + " (busiest)", f(cur[j])] for j in order[:2]]
                             + [[klab(keys[j], W['bucket'] == 'hour') + " (quietest)", f(cur[j])] for j in order[::-1][:2]], "note": ""}})
    for n, b in enumerate(breakdowns):
        q.append({"intent": "source", "id": f"b{n}", "text": b[2],
                  "answer": {"type": "table", "columns": [b[3], label], "rows": [[r[0], f(r[1])] for r in b[1]], "note": ""}})
    if nxt_q:
        q.append({"intent": "next", "id": "next", "text": "What should we look at next?",
                  "answer": {"type": "table", "columns": ["Observation", "Suggested check"], "rows": [list(nxt_q)], "note": ""}})
    q.append({"intent": "trust", "id": "source", "text": "Where does this number come from?",
              "answer": {"type": "table", "columns": ["Feed", "Fields", "Status"], "rows": [[source, fields, "Live figures"]], "note": ""}})
    q.append({"intent": "trust", "id": "caveats", "text": "What is excluded or uncertain?", "answer": {"type": "list", "items": caveats}})
    tip = ("Old site, same days" if old_prev else f"Previous {W['span']}") if prev is not None else None
    main = {"dates": keys, "series": {"fnb-performance": [{"date": k, "value": v} for k, v in zip(keys, cur)]}, "bucket": W["bucket"]}
    if prev is not None:
        main["previous"] = [{"date": k, "value": v} for k, v in zip(keys, prev)]
        main["tipLabel"] = tip
    if step_min:
        main["step"] = step_min
    if early_from:
        main["earlyFrom"] = early_from
    out = {"win": wkey, "sub": f"{sub_source or source}, {span}", "period": len(keys), "periodLabel": span,
           "through": keys[-1] if keys else None, "stats": stats,
           "health": [{"site": SITE_NAME, "statusLabel": "Live", "through": keys[-1] if keys else None, "via": source}],
           "main": main,
           "breakdowns": [{"id": f"b{n}", "title": b[0], "rows": [{"label": r[0], "value": r[1]} for r in b[1]]} for n, b in enumerate(breakdowns)],
           "patterns": pats, "questions": q,
           "raw": {"columns": [W["Bucket"] if "T" in (keys[0] if keys else "") else "Date", "Site", label] + (["Previous period"] if prev is not None else []),
                   "rows": [[k, SITE_NAME, v] + ([p] if prev is not None else []) for k, v, p in zip(keys, cur, prev or [None] * len(keys))]},
           "howCalculated": how}
    if extra:
        out.update(extra)
    return out


def level_bundle(wkey, *, label, unit, source, fields, keys, vals, prev_vals, breakdowns, how, caveats, sub_source=None,
                 step_min=None, early_from=None, compare_label=None):
    """A level reading (counted per bucket, not summed): latest bucket against the window's first, or the previous window."""
    W = WIN[wkey]
    have = [(k, v) for k, v in zip(keys, vals) if v is not None]
    tot = have[-1][1] if have else 0
    first = have[0][1] if have else 0
    x = tot - first
    when = klab(have[0][0], W["bucket"] == "hour") if have else ""
    stats = {"total": tot, "previousTotal": first, "change": None,
             "deltaText": ("Level with" if x == 0 else f"{'+' if x > 0 else '−'}{f(abs(x))} on") + f" {when}",
             "deltaTone": "up" if x > 0 else "down" if x < 0 else "",
             "railText": "level" if x == 0 else f"{'+' if x > 0 else '−'}{f(abs(x))}", "railTone": "up" if x > 0 else "down" if x < 0 else ""}
    span = span_label(keys, wkey, step_min)
    q = [{"intent": "status", "id": "total", "text": "What is the reading?",
          "answer": {"type": "stat", "value": f(tot), "label": label, "sub": stats["deltaText"]}}]
    for n, b in enumerate(breakdowns):
        q.append({"intent": "source", "id": f"b{n}", "text": b[2],
                  "answer": {"type": "table", "columns": [b[3], label], "rows": [[r[0], f(r[1])] for r in b[1]], "note": ""}})
    q.append({"intent": "trust", "id": "source", "text": "Where does this number come from?",
              "answer": {"type": "table", "columns": ["Feed", "Fields", "Status"], "rows": [[source, fields, "Live figures"]], "note": ""}})
    q.append({"intent": "trust", "id": "caveats", "text": "What is excluded or uncertain?", "answer": {"type": "list", "items": caveats}})
    main = {"dates": keys, "series": {"fnb-performance": [{"date": k, "value": v} for k, v in zip(keys, vals)]}, "bucket": W["bucket"],
            "heading": f"{W['Bucket']} by {W['bucket']}" if W["bucket"] != "day" else "Day by day"}
    if prev_vals is not None:
        main["previous"] = [{"date": k, "value": v} for k, v in zip(keys, prev_vals)]
        main["tipLabel"] = compare_label or f"Previous {W['span']}"
    if step_min:
        main["step"] = step_min
    if early_from:
        main["earlyFrom"] = early_from
    return {"win": wkey, "level": True, "sub": f"{sub_source or source}, {span}", "period": len(keys), "periodLabel": span,
            "through": keys[-1] if keys else None, "stats": stats,
            "health": [{"site": SITE_NAME, "statusLabel": "Live", "through": keys[-1] if keys else None, "via": source}],
            "main": main,
            "breakdowns": [{"id": f"b{n}", "title": b[0], "rows": [{"label": r[0], "value": r[1]} for r in b[1]]} for n, b in enumerate(breakdowns)],
            "patterns": [{"type": "movement", "title": f"{label} {'up' if x > 0 else 'down' if x < 0 else 'level'}{'' if x == 0 else ' ' + f(abs(x))} on {when}",
                          "evidence": f"{f(tot)} {unit} now against {f(first)} at the start of the window."}] if have else [],
            "questions": q,
            "raw": {"columns": [W["Bucket"], "Site", label], "rows": [[k, SITE_NAME, v] for k, v in zip(keys, vals)]},
            "howCalculated": how}


def day_window(end, wkey, launch):
    """Day keys of a day window and of the window before it ('all': from launch, no previous)."""
    if wkey == "all":
        n = max(1, (end - launch).days + 1)
        return [launch + dt.timedelta(days=i) for i in range(n)], None
    n = WIN[wkey]["n"]
    cur = [end - dt.timedelta(days=n - 1 - i) for i in range(n)]
    return cur, [d - dt.timedelta(days=n) for d in cur]


def nearest(wins, want):
    """The window a card shows when it cannot serve `want`: the nearest longer one, else the nearest shorter."""
    if want in wins:
        return want
    i = ORDER.index(want)
    for k in ORDER[i + 1:]:
        if k in wins:
            return k
    for k in reversed(ORDER[:i]):
        if k in wins:
            return k
    return wins[0] if wins else want
