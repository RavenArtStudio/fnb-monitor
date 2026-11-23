"""Daily snapshot for fnbperformance.com.

Reads Google Analytics 4, Search Console, a crawl of the live site and the
stored Semrush readings, then writes:

  data/cards.json             the card objects the desktop file draws
  data/history/YYYY-MM-DD.json the day's headline readings (site health lines)

Google access uses the service account key in the GOOGLE_SA_KEY secret.
Without it the Google cards are skipped and the rest still runs.
"""
import concurrent.futures as cf
import datetime as dt
import json
import os
import re
import sys
import threading
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import siteconf  # noqa: E402
from siteconf import CFG, SID, LANG_NAME, MAIN_LANG, OTHER_LANGS  # noqa: E402
SITE_NAME = CFG["name"]
import quality as Q  # noqa: E402
from windows import ORDER as WORDER, WIN, wbundle, level_bundle, day_window, klab, zkey, parse as wparse, span_label  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
# Site settings come from sites/<SITE_ID>.json (Checkpoint 30); FNB Performance keeps data/ itself.
DATA = siteconf.DATA
HIST = DATA / "history"
HIST.mkdir(parents=True, exist_ok=True)
SITE = CFG["url"]
GA_PROPERTY = CFG["ga_property"]
SC_SITE = CFG["sc_site"]
HOSTS = CFG["hosts"]
HOME = CFG.get("home", "/")
MARKET = CFG["market"]
CTA = CFG.get("cta", "enquiry")
ENQ = CFG["enquiries"]
K = "fnb-performance"              # internal series key the board reads for every site
UA = "fnb-monitor/1.0 (+https://github.com/RavenArtStudio/fnb-monitor)"

TODAY = dt.datetime.now(dt.timezone(dt.timedelta(hours=CFG.get("tz_hours", 4)))).date()   # the site's own time zone
GA = "Google Analytics"
SC = "Google Search Console"
CR = "Site crawl"
SM = "Semrush"
CONSENT = ("Google Analytics loads only after a visitor accepts cookies, so visitors "
           "who decline or ignore the banner are not counted.")
EVENT_NOTE = CFG.get("event_note", "seen in the site code")
GA_CAV = [CFG["ga_caveat"]] if CFG.get("ga_caveat") else []  # e.g. Analytics loads only after cookie consent

f = lambda n: f"{n:,}" if isinstance(n, int) else (f"{n:,.1f}" if isinstance(n, float) else str(n))
iso = lambda d: d.isoformat()
short = lambda d: f"{d.strftime('%b')} {d.day}"


page_name = Q.page_name


# ---------------------------------------------------------------- Google access
def google_session():
    raw = os.environ.get("GOOGLE_SA_KEY", "").strip()
    if not raw:
        print("GOOGLE_SA_KEY not set: Google cards skipped", file=sys.stderr)
        return None
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    creds = service_account.Credentials.from_service_account_info(
        json.loads(raw),
        scopes=["https://www.googleapis.com/auth/analytics.readonly",
                "https://www.googleapis.com/auth/webmasters.readonly",
                "openid"])   # openid: PageSpeed Insights on the project's own quota (24 Nov 2026)
    return AuthorizedSession(creds)


def host_filter(extra=None):
    hf = {"filter": {"fieldName": "hostName", "inListFilter": {"values": HOSTS}}}
    if not extra:
        return hf
    return {"andGroup": {"expressions": [hf, extra]}}


def ga(sess, start, end, dims, metrics, flt=None, limit=1000, order=None):
    body = {"dateRanges": [{"startDate": iso(start), "endDate": iso(end)}],
            "dimensions": [{"name": d} for d in dims],
            "metrics": [{"name": m} for m in metrics],
            "dimensionFilter": host_filter(flt), "limit": limit}
    if order:
        body["orderBys"] = [{"metric": {"metricName": order}, "desc": True}]
    r = sess.post(f"https://analyticsdata.googleapis.com/v1beta/properties/{GA_PROPERTY}:runReport",
                  json=body, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"GA {r.status_code}: {r.text[:300]}")
    out = []
    for row in r.json().get("rows", []):
        d = [v["value"] for v in row["dimensionValues"]]
        m = [float(v["value"]) for v in row["metricValues"]]
        out.append((d, m))
    return out


def sc(sess, start, end, dims, limit=1000, state="all"):
    url = ("https://searchconsole.googleapis.com/webmasters/v3/sites/"
           + requests.utils.quote(SC_SITE, safe="") + "/searchAnalytics/query")
    r = sess.post(url, json={"startDate": iso(start), "endDate": iso(end),
                             "dimensions": dims, "rowLimit": limit, "dataState": state}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"SC {r.status_code}: {r.text[:300]}")
    return r.json().get("rows", [])


def first_seen(sess):
    """First day with Search impressions (Search Console keeps 16 months) and with Analytics sessions,
    to check the configured launch date (22 Nov 2026)."""
    rows = sc(sess, TODAY - dt.timedelta(days=480), TODAY, ["date"], limit=1000)
    s_days = sorted(r["keys"][0] for r in rows if r.get("impressions", 0) > 0)
    rows = ga(sess, dt.date(2015, 8, 14), TODAY, ["date"], ["sessions"], limit=10000)
    g_days = sorted(d[0] for d, m in rows if m[0] > 0)
    return {"search": s_days[0] if s_days else None,
            "analytics": f"{g_days[0][:4]}-{g_days[0][4:6]}-{g_days[0][6:]}" if g_days else None}


# ---------------------------------------------------------------- card builders
LAUNCH = dt.date.fromisoformat(CFG["launch"])
CRAWL = {}


def prev_days_of(cur_days):
    return [d - dt.timedelta(days=len(cur_days)) for d in cur_days]


def window(end, n=7):
    cur = [end - dt.timedelta(days=n - 1 - i) for i in range(n)]
    prev = [d - dt.timedelta(days=n) for d in cur]
    return cur, prev


def card(id, label, unit, group, source, fields, cur_days, cur, prev, breakdowns, nxt, how,
         caveats, level=False, short_label=None, sub=None, precision=0):
    tot = cur[-1] if level else (round(sum(cur), precision) if precision else int(sum(cur)))
    ptot = prev[-1] if level else (round(sum(prev), precision) if precision else int(sum(prev)))
    diff = tot - ptot
    pct = round(100 * diff / ptot) if ptot else None
    avg = round(tot / len(cur), 1)
    stats = {"total": tot, "previousTotal": ptot, "change": None if level else pct, "avgPerDay": avg}
    if level:
        stats["deltaText"] = ("Level with" if diff == 0 else f"{'+' if diff > 0 else '−'}{f(abs(diff))} on") + " a week earlier"
        stats["deltaTone"] = "up" if diff > 0 else "down" if diff < 0 else ""
    elif pct is None and ptot == 0 and tot > 0:
        stats["deltaText"] = f"{f(tot)} against none in the previous {len(cur)} days"
        stats["deltaTone"] = "up"
        stats["railText"], stats["railTone"] = "new", "up"
    pats = []
    old = cur_days and prev_days_of(cur_days)[-1] < LAUNCH
    if level:
        pats.append({"type": "movement",
                     "title": f"{label} {'up' if diff > 0 else 'down' if diff < 0 else 'level'}{'' if diff == 0 else ' ' + f(abs(diff))} on a week earlier",
                     "evidence": f"{f(tot)} on {short(cur_days[-1])} against {f(ptot)} on {short(cur_days[-1] - dt.timedelta(days=7))}."})
    else:
        if pct is not None:
            pats.append({"type": "movement",
                         "title": f"{label} {'up' if pct > 0 else 'down' if pct < 0 else 'level'}{'' if pct == 0 else ' ' + str(abs(pct)) + '%'} on the previous {len(cur)} days",
                         "evidence": f"{f(tot)} {unit} against {f(ptot)} in the {len(cur)} days before."})
        mx = max(cur) if cur else 0
        if mx > 1:
            pats.append({"type": "peak", "title": f"Strongest day was {short(cur_days[cur.index(mx)])}",
                         "evidence": f"{f(mx)} {unit}, against a daily average of {avg}."})
    if old:
        part = cur_days[0] < LAUNCH
        pats.append({"type": "caution", "title": "Compared with the old site",
                     "evidence": f"The new site went live on {short(LAUNCH)}. The previous {len(cur)} days are the old site"
                                 + (", and so are the days before launch in this window." if part else ".")
                                 + (" Google usually takes two to four weeks to re-crawl and settle after a relaunch." if source == SC else "")})
    for b in breakdowns:
        s = sum(r[1] for r in b[1])
        if s and len(b[1]) > 1 and b[1][0][1] / s >= .45:
            pats.append({"type": "concentration", "title": f"{b[1][0][0]} accounts for {round(100 * b[1][0][1] / s)}%",
                         "evidence": f"{f(b[1][0][1])} of {f(s)} under “{b[0]}”."})
            break
    order = sorted(range(len(cur)), key=lambda j: -cur[j])
    q = [{"intent": "status", "id": "total", "text": "What is the reading?",
          "answer": {"type": "stat", "value": f(tot),
                     "label": f"{label}, {'on ' + short(cur_days[-1]) if level else 'last ' + str(len(cur)) + ' days'}",
                     "sub": stats.get("deltaText") or (f"{avg} per day, {'+' if pct and pct > 0 else ''}{pct}% vs the previous {len(cur)} days" if pct is not None else "")}},
         {"intent": "change", "id": "compare", "text": "How does this compare with before?",
          "answer": {"type": "table", "columns": ["Period", label],
                     "rows": [["Latest" if level else f"Latest {len(cur)} days", f(tot)],
                              ["A week earlier" if level else f"Previous {len(cur)} days", f(ptot)],
                              ["Change", (("+" if diff > 0 else "") + f(diff)) if level or pct is None else (("+" if pct > 0 else "") + str(pct) + "%")]],
                     "note": ""}}]
    if not level and any(cur):
        q.append({"intent": "change", "id": "days", "text": "Which days were strongest and weakest?",
                  "answer": {"type": "table", "columns": ["Day", "Value"],
                             "rows": [[short(cur_days[j]) + " (best)", f(cur[j])] for j in order[:2]]
                             + [[short(cur_days[j]) + " (weakest)", f(cur[j])] for j in order[::-1][:2]], "note": ""}})
    for n, b in enumerate(breakdowns):
        q.append({"intent": "source", "id": f"b{n}", "text": b[2],
                  "answer": {"type": "table", "columns": [b[3], label], "rows": [[r[0], f(r[1])] for r in b[1]], "note": ""}})
    if nxt:
        q.append({"intent": "next", "id": "next", "text": "What should we look at next?",
                  "answer": {"type": "table", "columns": ["Observation", "Suggested check"], "rows": [list(nxt)], "note": ""}})
    q.append({"intent": "trust", "id": "source", "text": "Where does this number come from?",
              "answer": {"type": "table", "columns": ["Feed", "Fields", "Status"], "rows": [[source, fields, "Live figures"]], "note": ""}})
    q.append({"intent": "trust", "id": "caveats", "text": "What is excluded or uncertain?", "answer": {"type": "list", "items": caveats}})
    days = [iso(d) for d in cur_days]
    return {"id": id, "group": group, "status": "live", "source": source, "short": short_label or label, "level": level,
            "sub": sub or f"{source}, {short(cur_days[0])} to {short(cur_days[-1])}",
            "available": True, "brand": K, "period": len(cur), "periodLabel": f"{short(cur_days[0])} to {short(cur_days[-1])}", "label": label, "unit": unit, "through": days[-1],
            "stats": stats,
            "health": [{"site": SITE_NAME, "statusLabel": "Live", "through": days[-1], "via": source}],
            "main": {"dates": days, "series": {K: [{"date": d, "value": v} for d, v in zip(days, cur)]},
                     "previous": [{"date": d, "value": v} for d, v in zip(days, prev)],
                     "tipLabel": ("Old site, a week earlier" if level else "Old site, same days") if old else ("A week earlier" if level else f"Previous {len(cur)} days")},
            "breakdowns": [{"id": f"b{n}", "title": b[0], "rows": [{"label": r[0], "value": r[1]} for r in b[1]]} for n, b in enumerate(breakdowns)],
            "patterns": pats, "questions": q,
            "raw": {"columns": ["Date", "Site", label, "Previous period"],
                    "rows": [[d, SITE_NAME, v, p] for d, v, p in zip(days, cur, prev)]},
            "howCalculated": how}


def reading(id, label, short_label, unit, group, source, fields, dates, vals, sub, breakdowns, nxt, how,
            caveats, heading="Day by day", pats=None, lower_better=False):
    """Card for a level reading over stored history (crawl, Semrush). None = no reading that day."""
    have = [(d, v) for d, v in zip(dates, vals) if v is not None]
    tot = have[-1][1]
    prior = have[-2] if len(have) > 1 else None
    if prior is None:
        delta, rail, tone = f"First reading, {klab(have[-1][0], True)}", "new", ""
    else:
        x = tot - prior[1]
        when = klab(prior[0], True)
        delta = "Level with " + when if x == 0 else f"{'+' if x > 0 else '−'}{f(abs(x))} on {when}"
        rail = "level" if x == 0 else f"{'+' if x > 0 else '−'}{f(abs(x))}"
        good = (x < 0) if lower_better else (x > 0)
        tone = "" if x == 0 else ("up" if good else "down")
        if pats is None:
            pats = [{"type": "movement", "title": f"{label} {'up' if x > 0 else 'down' if x < 0 else 'level'}{'' if x == 0 else ' ' + f(abs(x))} on {when}",
                     "evidence": f"{f(tot)} {unit} against {f(prior[1])} on {when}."}]
    q = [{"intent": "status", "id": "total", "text": "What is the reading?",
          "answer": {"type": "stat", "value": f(tot), "label": label, "sub": delta}}]
    for n, b in enumerate(breakdowns):
        q.append({"intent": "source", "id": f"b{n}", "text": b[2],
                  "answer": {"type": "table", "columns": [b[3], b[4]], "rows": [[r[0], f(r[1])] for r in b[1]], "note": ""}})
    if nxt:
        q.append({"intent": "next", "id": "next", "text": "What should we look at next?",
                  "answer": {"type": "table", "columns": ["Observation", "Suggested check"], "rows": [list(nxt)], "note": ""}})
    q.append({"intent": "trust", "id": "source", "text": "Where does this number come from?",
              "answer": {"type": "table", "columns": ["Feed", "Fields", "Status"], "rows": [[source, fields, "Live figures"]], "note": ""}})
    q.append({"intent": "trust", "id": "caveats", "text": "What is excluded or uncertain?", "answer": {"type": "list", "items": caveats}})
    return {"id": id, "group": group, "status": "live", "source": source, "short": short_label, "level": True, "sub": sub,
            "available": True, "brand": K, "period": len(dates), "periodLabel": "monthly readings" if heading == "Month by month" else "daily readings", "label": label, "unit": unit, "through": have[-1][0],
            "stats": {"total": tot, "previousTotal": prior[1] if prior else None, "change": None,
                      "deltaText": delta, "deltaTone": tone, "railText": rail, "railTone": tone},
            "health": [{"site": SITE_NAME, "statusLabel": "Live", "through": have[-1][0], "via": source}],
            "main": {"dates": dates, "heading": heading, "series": {K: [{"date": d, "value": v} for d, v in zip(dates, vals)]}},
            "breakdowns": [{"id": f"b{n}", "title": b[0], "rows": [{"label": r[0], "value": r[1]} for r in b[1]]} for n, b in enumerate(breakdowns)],
            "patterns": pats or [], "questions": q,
            "raw": {"columns": ["Date", "Site", label], "rows": [[d, SITE_NAME, v] for d, v in zip(dates, vals)]},
            "howCalculated": how}


def series(rows, days, key=lambda d: d[0], val=lambda m: m[0]):
    by = {}
    for d, m in rows:
        day = dt.datetime.strptime(key(d), "%Y%m%d").date()
        by[day] = by.get(day, 0) + val(m)
    return [int(by.get(day, 0)) for day in days]


def tidy(x):
    x = str(x)
    if x in ("(not set)", "", "(other)"):
        return "Not recorded"
    return x[:1].upper() + x[1:] if x.islower() else x


def top(rows, n=6, label=lambda d: d[0], other=True):
    agg = {}
    for d, m in rows:
        k = tidy(label(d))
        agg[k] = agg.get(k, 0) + int(m[0])
    items = sorted(((k, v) for k, v in agg.items() if v > 0), key=lambda x: -x[1])
    if other and len(items) > n:
        rest = sum(v for _, v in items[n - 1:])
        items = items[:n - 1] + [("Other", rest)]
    return items[:n]


# ---------------------------------------------------------------- Google Analytics cards
def ga_cards(sess):
    end = TODAY - dt.timedelta(days=1)
    cur_days, prev_days = window(end)
    start, w0 = prev_days[0], cur_days[0]
    cards = []
    fx = lambda caveats: caveats + [CONSENT]

    # Enquiries: the site's own funnel events, as listed in sites/<id>.json
    names = sorted({e for q in ENQ for e in q["events"]})
    ev = ga(sess, start, end, ["date", "eventName"], ["eventCount"],
            {"filter": {"fieldName": "eventName", "inListFilter": {"values": names}}})
    def ev_series(evn, days):
        return [sum(v) for v in zip(*[series([(d, m) for d, m in ev if d[1] == n], days) for n in evn])]
    def ev_break(evn, dims):
        try:
            return ga(sess, w0, end, dims, ["eventCount"],
                      {"filter": {"fieldName": "eventName", "inListFilter": {"values": evn}}}, order="eventCount")
        except RuntimeError as e:
            print(e, file=sys.stderr)
            return []
    dims_used = {}
    for q in ENQ:
        bks, fields, extra = [], [f"eventName = {' or '.join(q['events'])}", "eventCount"], []
        for dim, ttl, ques, colname in q["breakdowns"]:
            rows, dname = ev_break(q["events"], [dim]), dim
            if dim.startswith("customEvent:") and (not rows or all(d[0] in ("(not set)", "") for d, _ in rows)):
                rows, dname = ev_break(q["events"], ["pagePath"]), "pagePath"
                if q.get("param_fallback"):
                    extra.append(q["param_fallback"])
            dims_used[(q["id"], dim)] = dname
            bks.append((ttl, top(rows, 8 if q.get("kind") == "tool" else 6, label=enq_label(dname)), ques, colname))
            fields.append(dname)
        cur, prev = ev_series(q["events"], cur_days), ev_series(q["events"], prev_days)
        nxt = (f"{sum(cur)} {q['unit']} this week", q["reading"]) if q.get("reading") else None
        cav = [c.replace("{note}", EVENT_NOTE) for c in q.get("caveats", [])] + extra
        cards.append(card(q["id"], q["label"], q["unit"], "Enquiries", GA, ", ".join(fields), cur_days, cur, prev, bks, nxt,
                          q["how"], fx(cav), short_label=q["label"]))

    # Website
    daily = ga(sess, start, end, ["date"], ["sessions", "engagedSessions", "newUsers", "screenPageViews"])
    col = lambda i, days: series(daily, days, val=lambda m: m[i])
    ch = ga(sess, w0, end, ["sessionDefaultChannelGroup"], ["sessions"], order="sessions")
    cty = ga(sess, w0, end, ["country"], ["sessions"], order="sessions")
    lp = ga(sess, w0, end, ["landingPage"], ["sessions"], order="sessions", limit=50)
    dev = ga(sess, w0, end, ["deviceCategory"], ["sessions"], order="sessions")
    s_c, s_p = col(0, cur_days), col(0, prev_days)
    mk = sum(int(m[0]) for d, m in cty if d[0] in MARKET["countries"])
    cards.append(card("sessions", "Website sessions", "sessions", "Website", GA,
        "date, sessions, sessionDefaultChannelGroup, country, landingPage, deviceCategory", cur_days, s_c, s_p,
        [("Where visitors come from", top(ch), "Where do visitors come from?", "Channel"),
         ("Country", top(cty), "Which countries are they in?", "Country"),
         ("Entry page", top(lp, label=lambda d: page_name(d[0])), "Which pages do visits start on?", "Entry page"),
         ("Device", top(dev), "What are they browsing on?", "Device")],
        (f"{mk} of {sum(s_c)} sessions from {MARKET['the']}", f"The {MARKET['label']} share is the one that matters; the rest is partly the team."),
        "Sessions on the live site hostnames. The previous period is the 7 days immediately before.",
        fx(GA_CAV + ["Visits from development hosts are excluded.", "Visits by the team count until internal traffic is filtered in Google Analytics."])))

    eng = ga(sess, w0, end, ["landingPage"], ["engagedSessions"], order="engagedSessions", limit=50)
    e_c, e_p = col(1, cur_days), col(1, prev_days)
    cards.append(card("engaged", "Engaged sessions", "sessions", "Website", GA,
        "date, engagedSessions, landingPage", cur_days, e_c, e_p,
        [("Entry page of engaged sessions", top(eng, label=lambda d: page_name(d[0])), "Which entry pages hold attention?", "Entry page")],
        (f"{sum(e_c)} of {sum(s_c)} sessions stayed to read", "Compare the entry pages that hold visitors with the ones that lose them."),
        "Sessions that lasted over 10 seconds, viewed two or more pages, or fired a key event.", fx(GA_CAV)))

    nvr = ga(sess, w0, end, ["newVsReturning"], ["activeUsers"], order="activeUsers")
    ncty = ga(sess, w0, end, ["country"], ["newUsers"], order="newUsers")
    n_c, n_p = col(2, cur_days), col(2, prev_days)
    cards.append(card("newvisitors", "New visitors", "visitors", "Website", GA,
        "date, newUsers, newVsReturning, country", cur_days, n_c, n_p,
        [("New against returning", top(nvr, label=lambda d: d[0].capitalize() if d[0] else "Unknown"), "How many are new?", "Visitor"),
         ("Country of new visitors", top(ncty), "Where are new visitors from?", "Country")],
        None, "People with no earlier visit to the site.",
        fx(GA_CAV + ["Team members count as new on each new device until internal traffic is filtered."])))

    pv = ga(sess, w0, end, ["pagePath"], ["screenPageViews"], order="screenPageViews", limit=50)
    v_c, v_p = col(3, cur_days), col(3, prev_days)
    cards.append(card("views", "Page views", "views", "Website", GA,
        "date, screenPageViews, pagePath", cur_days, v_c, v_p,
        [("By page", top(pv, 8, label=lambda d: page_name(d[0])), "Which pages are viewed most?", "Page")],
        None, "Every page load on the live site, repeats included.", fx(GA_CAV)))
    try:
        ga_windows(sess, cards, end, dims_used)
    except Exception as e:
        print("GA windows:", e, file=sys.stderr)
    return cards


def enq_label(dname):
    if dname in ("pagePath", "landingPage"):
        return lambda d: page_name(d[0])
    if dname.startswith("customEvent:"):
        return lambda d: d[0].replace("-", " ").capitalize()
    if dname == "eventName":
        return lambda d: d[0].replace("_widget_open", " demo").replace("_", " ").capitalize()
    return lambda d: d[0] or "Not set"


def attach(c, wkey, bundle):
    """Add a window's view to a card. The card's own fields stay the 7-day view."""
    c.setdefault("w", {})[wkey] = bundle
    wins = set(c.get("wins") or ["7d"]) | {wkey}
    c["wins"] = [k for k in WORDER if k in wins]


def ga_windows(sess, cards, end, dims_used):
    """30 days and since launch for the Analytics cards, from the processed daily reports."""
    by = {c["id"]: c for c in cards}
    span0 = min(end - dt.timedelta(days=59), LAUNCH)
    names = sorted({e for q in ENQ for e in q["events"]})
    ev = ga(sess, span0, end, ["date", "eventName"], ["eventCount"],
            {"filter": {"fieldName": "eventName", "inListFilter": {"values": names}}})
    daily = ga(sess, span0, end, ["date"], ["sessions", "engagedSessions", "newUsers", "screenPageViews"])
    fx = lambda caveats: caveats + [CONSENT]

    def safe(*a, **k):
        try:
            return ga(sess, *a, **k)
        except RuntimeError as e:
            print(e, file=sys.stderr)
            return []

    for wkey in ("30d", "all"):
        cur_days, prev_days = day_window(end, wkey, LAUNCH)
        w0 = cur_days[0]
        keys = [iso(d) for d in cur_days]
        old_prev = bool(prev_days) and prev_days[-1] < LAUNCH
        old_part = cur_days[0] < LAUNCH
        evs = lambda evn, days: [sum(v) for v in zip(*[series([(d, m) for d, m in ev if d[1] == n], days) for n in evn])] if days else None
        col = lambda i, days: series(daily, days, val=lambda m: m[i]) if days else None
        evb = lambda evn, dims: safe(w0, end, dims, ["eventCount"], {"filter": {"fieldName": "eventName", "inListFilter": {"values": evn}}}, order="eventCount")
        common = dict(keys=keys, old_prev=old_prev, old_part=old_part, launch=LAUNCH, sub_source=GA)
        span_note = "since the launch" if wkey == "all" else "over 30 days"
        defs = {}
        for q in ENQ:
            bks, used = [], []
            for dim, ttl, ques, colname in q["breakdowns"]:
                dname = dims_used.get((q["id"], dim), dim)
                used.append(dname)
                bks.append((ttl, top(evb(q["events"], [dname]), 8 if q.get("kind") == "tool" else 6, label=enq_label(dname)), ques, colname))
            defs[q["id"]] = dict(label=q["label"], unit=q["unit"], fields=", ".join([f"eventName = {' or '.join(q['events'])}", "eventCount"] + used),
                                 cur=evs(q["events"], cur_days), prev=evs(q["events"], prev_days), breakdowns=bks, how=q["how"],
                                 caveats=fx([c.replace("{note}", EVENT_NOTE) for c in q.get("caveats", [])[1:]]))
        defs.update({
            "sessions": dict(label="Website sessions", unit="sessions", fields="date, sessions, sessionDefaultChannelGroup, country, landingPage, deviceCategory",
                             cur=col(0, cur_days), prev=col(0, prev_days),
                             breakdowns=[("Where visitors come from", top(safe(w0, end, ["sessionDefaultChannelGroup"], ["sessions"], order="sessions")), "Where do visitors come from?", "Channel"),
                                         ("Country", top(safe(w0, end, ["country"], ["sessions"], order="sessions")), "Which countries are they in?", "Country"),
                                         ("Entry page", top(safe(w0, end, ["landingPage"], ["sessions"], order="sessions", limit=50), label=lambda d: page_name(d[0])), "Which pages do visits start on?", "Entry page"),
                                         ("Device", top(safe(w0, end, ["deviceCategory"], ["sessions"], order="sessions")), "What are they browsing on?", "Device")],
                             how=f"Sessions on the live site hostnames, {span_note}.",
                             caveats=fx(GA_CAV + ["Visits by the team count until internal traffic is filtered in Google Analytics."])),
            "engaged": dict(label="Engaged sessions", unit="sessions", fields="date, engagedSessions, landingPage",
                            cur=col(1, cur_days), prev=col(1, prev_days),
                            breakdowns=[("Entry page of engaged sessions", top(safe(w0, end, ["landingPage"], ["engagedSessions"], order="engagedSessions", limit=50), label=lambda d: page_name(d[0])), "Which entry pages hold attention?", "Entry page")],
                            how="Sessions that lasted over 10 seconds, viewed two or more pages, or fired a key event.", caveats=fx(GA_CAV)),
            "newvisitors": dict(label="New visitors", unit="visitors", fields="date, newUsers, newVsReturning, country",
                                cur=col(2, cur_days), prev=col(2, prev_days),
                                breakdowns=[("New against returning", top(safe(w0, end, ["newVsReturning"], ["activeUsers"], order="activeUsers"), label=lambda d: d[0].capitalize() if d[0] else "Unknown"), "How many are new?", "Visitor"),
                                            ("Country of new visitors", top(safe(w0, end, ["country"], ["newUsers"], order="newUsers")), "Where are new visitors from?", "Country")],
                                how="People with no earlier visit to the site.",
                                caveats=fx(GA_CAV + ["Team members count as new on each new device until internal traffic is filtered."])),
            "views": dict(label="Page views", unit="views", fields="date, screenPageViews, pagePath",
                          cur=col(3, cur_days), prev=col(3, prev_days),
                          breakdowns=[("By page", top(safe(w0, end, ["pagePath"], ["screenPageViews"], order="screenPageViews", limit=50), 8, label=lambda d: page_name(d[0])), "Which pages are viewed most?", "Page")],
                          how="Every page load on the live site, repeats included.", caveats=fx(GA_CAV)),
        })
        for cid, d in defs.items():
            if cid in by:
                attach(by[cid], wkey, wbundle(wkey, source=GA, **common, **d))


# ---------------------------------------------------------------- Search Console cards
def sc_cards(sess):
    rows = sc(sess, TODAY - dt.timedelta(days=30), TODAY - dt.timedelta(days=1), ["date"])
    if not rows:
        return []
    last = max(dt.date.fromisoformat(r["keys"][0]) for r in rows)
    cur_days, prev_days = window(last)
    # Early figures: days after the latest day Google has finalised; Google still adds to them.
    fin = sc(sess, TODAY - dt.timedelta(days=30), TODAY - dt.timedelta(days=1), ["date"], state="final")
    last_final = max((dt.date.fromisoformat(r["keys"][0]) for r in fin), default=None)
    early = [d for d in cur_days if last_final is None or d > last_final]
    span = (short(early[0]) if len(early) == 1 else f"{short(early[0])} to {short(early[-1])}") if early else ""
    by = {dt.date.fromisoformat(r["keys"][0]): r for r in rows}
    get = lambda days, k: [int(by[d][k]) if d in by else 0 for d in days]
    w = (cur_days[0], last)
    q = sc(sess, *w, ["query"], 200)
    pg = sc(sess, *w, ["page"], 100)
    qtop = lambda k: [(r["keys"][0], int(r[k])) for r in sorted(q, key=lambda r: -r[k]) if r[k] > 0][:6]
    ptop = lambda k: [(page_name(urlparse(r["keys"][0]).path), int(r[k])) for r in sorted(pg, key=lambda r: -r[k]) if r[k] > 0][:6]
    lag = [(f"Google reports search data two to three days late. {span} {'is an early figure' if len(early) == 1 else 'are early figures'} "
            "that Google usually raises over the next two days.") if early else
           "Google reports search data two to three days late, so the window ends on the latest complete day.",
           "Rare queries are withheld by Google for privacy, so query rows add up to less than the total."]
    sub = f"{SC}, {short(cur_days[0])} to {short(last)}" + (f", {span} early" if early else "")
    imp_c, imp_p = get(cur_days, "impressions"), get(prev_days, "impressions")
    clk_c, clk_p = get(cur_days, "clicks"), get(prev_days, "clicks")
    cards = [card("impressions", "Search impressions", "impressions", "Google Search", SC, "date, impressions, query, page",
                  cur_days, imp_c, imp_p,
                  [("By search query", qtop("impressions"), "Which searches show the site?", "Query"),
                   ("By page shown", ptop("impressions"), "Which pages does Google show?", "Page")],
                  (f"Shown {f(sum(imp_c))} times, clicked {f(sum(clk_c))} times",
                   "Rewrite the titles and descriptions of the most shown pages first."),
                  "Times any page of the site appeared in Google results.", lag, sub=sub),
             card("searchclicks", "Search clicks", "clicks", "Google Search", SC, "date, clicks, query, page",
                  cur_days, clk_c, clk_p,
                  [("By search query", qtop("clicks"), "Which searches bring visits?", "Query"),
                   ("By page", ptop("clicks"), "Which pages get the clicks?", "Page")],
                  None, "Clicks from Google results to the site.", lag, sub=sub)]
    # Keywords on page one: per day, queries with average position 10 or better
    qd = sc(sess, prev_days[0], last, ["date", "query"], 5000)
    cnt = {}
    for r in qd:
        if r["position"] <= 10:
            d = dt.date.fromisoformat(r["keys"][0])
            cnt[d] = cnt.get(d, 0) + 1
    p1_c = [cnt.get(d, 0) for d in cur_days]
    p1_p = [cnt.get(d, 0) for d in prev_days]
    near = sorted([r for r in q if 10 < r["position"] <= 20], key=lambda r: -r["impressions"])[:5]
    cards.append(card("pageone", "Keywords on page one", "keywords", "Google Search", SC,
                      "date, query, position (count of queries at 10 or better)", cur_days, p1_c, p1_p,
                      [("Closest to page one, by impressions",
                        [(f"{r['keys'][0]} (position {round(r['position'])})", int(r["impressions"])) for r in near],
                        "Which keywords are closest to page one?", "Query")],
                      ("Keywords at positions 11 to 20 are the cheapest gains", "Strengthen those pages first.") if near else None,
                      "Number of search queries where the site ranked in the first ten results that day. Compared with the same day a week earlier.",
                      ["Position is the average across all searches that day, so a keyword can move in and out of the count."] + lag[:1],
                      level=True, sub=sub))
    if early:
        for c in cards:
            mark_early(c, early, span)
    try:
        sc_windows(sess, cards, last, last_final)
    except Exception as e:
        print("SC windows:", e, file=sys.stderr)
    return cards


def sc_raw(sess, start, end, dims, limit=1000, state="all"):
    url = ("https://searchconsole.googleapis.com/webmasters/v3/sites/"
           + requests.utils.quote(SC_SITE, safe="") + "/searchAnalytics/query")
    r = sess.post(url, json={"startDate": iso(start), "endDate": iso(end),
                             "dimensions": dims, "rowLimit": limit, "dataState": state}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"SC {r.status_code}: {r.text[:300]}")
    return r.json()


def sc_windows(sess, cards, last, last_final):
    """30 days and since launch by day; 12 and 24 hours by hour (Google's hourly data, partial for the latest hours)."""
    by = {c["id"]: c for c in cards}
    lag = "Google reports search data hours to days late; the latest figures are early and usually rise."
    priv = "Rare queries are withheld by Google for privacy, so query rows add up to less than the total."
    rows = sc(sess, min(last - dt.timedelta(days=60), LAUNCH), last, ["date"])
    dby = {dt.date.fromisoformat(r["keys"][0]): r for r in rows}
    get = lambda days, k: [int(dby[d][k]) if d in dby else 0 for d in days] if days else None
    for wkey in ("30d", "all"):
        cur_days, prev_days = day_window(last, wkey, LAUNCH)
        w = (cur_days[0], last)
        q = sc(sess, *w, ["query"], 200)
        pg = sc(sess, *w, ["page"], 100)
        qtop = lambda k: [(r["keys"][0], int(r[k])) for r in sorted(q, key=lambda r: -r[k]) if r[k] > 0][:6]
        ptop = lambda k: [(page_name(urlparse(r["keys"][0]).path), int(r[k])) for r in sorted(pg, key=lambda r: -r[k]) if r[k] > 0][:6]
        early = next((iso(d) for d in cur_days if last_final is None or d > last_final), None)
        common = dict(keys=[iso(d) for d in cur_days], old_prev=bool(prev_days) and prev_days[-1] < LAUNCH,
                      old_part=cur_days[0] < LAUNCH, launch=LAUNCH, early_from=early, sub_source=SC)
        if "impressions" in by:
            attach(by["impressions"], wkey, wbundle(wkey, label="Search impressions", unit="impressions", source=SC, fields="date, impressions, query, page",
                   cur=get(cur_days, "impressions"), prev=get(prev_days, "impressions"),
                   breakdowns=[("By search query", qtop("impressions"), "Which searches show the site?", "Query"),
                               ("By page shown", ptop("impressions"), "Which pages does Google show?", "Page")],
                   how="Times any page of the site appeared in Google results.", caveats=[lag, priv], **common))
        if "searchclicks" in by:
            attach(by["searchclicks"], wkey, wbundle(wkey, label="Search clicks", unit="clicks", source=SC, fields="date, clicks, query, page",
                   cur=get(cur_days, "clicks"), prev=get(prev_days, "clicks"),
                   breakdowns=[("By search query", qtop("clicks"), "Which searches bring visits?", "Query"),
                               ("By page", ptop("clicks"), "Which pages get the clicks?", "Page")],
                   how="Clicks from Google results to the site.", caveats=[lag, priv], **common))
        if "pageone" in by:
            qd = sc(sess, (prev_days or cur_days)[0], last, ["date", "query"], 25000)
            cnt = {}
            for r in qd:
                if r["position"] <= 10:
                    d = dt.date.fromisoformat(r["keys"][0])
                    cnt[d] = cnt.get(d, 0) + 1
            near = sorted([r for r in q if 10 < r["position"] <= 20], key=lambda r: -r["impressions"])[:5]
            attach(by["pageone"], wkey, level_bundle(wkey, label="Keywords on page one", unit="keywords", source=SC,
                   fields="date, query, position (count of queries at 10 or better)", keys=[iso(d) for d in cur_days],
                   vals=[cnt.get(d, 0) for d in cur_days], prev_vals=[cnt.get(d, 0) for d in prev_days] if prev_days else None,
                   breakdowns=[("Closest to page one, by impressions", [(f"{r['keys'][0]} (position {round(r['position'])})", int(r["impressions"])) for r in near],
                                "Which keywords are closest to page one?", "Query")],
                   how="Number of search queries where the site ranked in the first ten results that day.",
                   caveats=["Position is the average across all searches that day, so a keyword can move in and out of the count.", lag],
                   sub_source=SC, early_from=early, compare_label="Old site, 30 days earlier" if prev_days and prev_days[-1] < LAUNCH else None))

    # Hourly: up to 10 days back, partial for the latest hours.
    now = dt.datetime.now(dt.timezone.utc)
    end_h = now.replace(minute=0, second=0, microsecond=0) - dt.timedelta(hours=1)
    HOUR = "HOUR"
    try:
        hj = sc_raw(sess, (now - dt.timedelta(days=3)).date(), now.date(), [HOUR], 500, state="HOURLY_ALL")
    except RuntimeError:
        HOUR = "hour"
        hj = sc_raw(sess, (now - dt.timedelta(days=3)).date(), now.date(), [HOUR], 500, state="HOURLY_ALL")
    hk = lambda s: zkey(dt.datetime.fromisoformat(s))
    hby = {hk(r["keys"][0]): r for r in hj.get("rows", [])}
    meta = hj.get("metadata") or {}
    inc = meta.get("firstIncompleteHour")
    if inc:
        inc = hk(inc)
    elif hby:
        inc = zkey(max(dt.datetime.strptime(k, "%Y-%m-%dT%H:%MZ") for k in hby).replace(tzinfo=dt.timezone.utc) + dt.timedelta(hours=1))
    try:
        hq = sc_raw(sess, (now - dt.timedelta(days=3)).date(), now.date(), [HOUR, "query"], 25000, state="HOURLY_ALL").get("rows", [])
    except RuntimeError as e:
        print("SC hourly by query:", e, file=sys.stderr)
        hq = None
    for wkey in ("12h", "24h"):
        n = WIN[wkey]["n"]
        hours = [end_h - dt.timedelta(hours=n - 1 - i) for i in range(n)]
        keys = [zkey(h) for h in hours]
        pkeys = [zkey(h - dt.timedelta(hours=n)) for h in hours]
        val = lambda ks, k: [int(hby[x][k]) if x in hby else 0 for x in ks]
        early = next((x for x in keys if inc and x >= inc), None)
        inw = set(keys)
        def qtop(k):
            if hq is None:
                return []
            agg = {}
            for r in hq:
                if hk(r["keys"][0]) in inw and r[k] > 0:
                    agg[r["keys"][1]] = agg.get(r["keys"][1], 0) + int(r[k])
            return sorted(agg.items(), key=lambda x: -x[1])[:6]
        cav = ["Google's hourly figures are partial for the latest hours and usually rise over the next day.", priv]
        common = dict(keys=keys, step_min=60, early_from=early, sub_source=f"{SC}, by hour", launch=LAUNCH)
        if "impressions" in by:
            attach(by["impressions"], wkey, wbundle(wkey, label="Search impressions", unit="impressions", source=SC, fields="HOUR, impressions, query (dataState HOURLY_ALL)",
                   cur=val(keys, "impressions"), prev=val(pkeys, "impressions"),
                   breakdowns=[("By search query", qtop("impressions"), "Which searches show the site?", "Query")] if hq is not None else [],
                   how="Times any page of the site appeared in Google results, by hour.", caveats=cav, **common))
        if "searchclicks" in by:
            attach(by["searchclicks"], wkey, wbundle(wkey, label="Search clicks", unit="clicks", source=SC, fields="HOUR, clicks, query (dataState HOURLY_ALL)",
                   cur=val(keys, "clicks"), prev=val(pkeys, "clicks"),
                   breakdowns=[("By search query", qtop("clicks"), "Which searches bring visits?", "Query")] if hq is not None else [],
                   how="Clicks from Google results to the site, by hour.", caveats=cav, **common))
        if "pageone" in by and hq is not None:
            cnt = {}
            for r in hq:
                if r["position"] <= 10:
                    x = hk(r["keys"][0])
                    cnt[x] = cnt.get(x, 0) + 1
            attach(by["pageone"], wkey, level_bundle(wkey, label="Keywords on page one", unit="keywords", source=SC,
                   fields="HOUR, query, position (count of queries at 10 or better)", keys=keys,
                   vals=[cnt.get(x, 0) for x in keys], prev_vals=[cnt.get(x, 0) for x in pkeys], breakdowns=[],
                   how="Number of search queries where the site ranked in the first ten results in that hour.",
                   caveats=["An hour has few searches, so the count moves more than the daily one.", cav[0]],
                   sub_source=f"{SC}, by hour", step_min=60, early_from=early))


def mark_early(c, early, span):
    """Flag days Google has not finalised: shaded band on the chart, a caution, the source status."""
    one = len(early) == 1
    c["main"]["earlyFrom"] = iso(early[0])
    c["early"] = [iso(d) for d in early]
    c["patterns"].insert(1 if c["patterns"] else 0, {
        "type": "caution", "title": f"{span} {'is an early figure' if one else 'are early figures'}",
        "evidence": f"Google is still counting {'this day' if one else 'these days'} and usually adds to the figure "
                    "over the next two days" + (f", so the count on {short(early[-1])} can still move." if c["level"]
                    else ", so the change against the previous days reads low until it settles.")})
    for q in c["questions"]:
        if q["id"] == "source":
            q["answer"]["rows"][0][2] = f"Live figures, {span} early"


# ---------------------------------------------------------------- Cube inputs from Google
def target_presence(sess):
    t = json.loads((DATA / "targets.json").read_text())
    rows = sc(sess, TODAY - dt.timedelta(days=30), TODAY - dt.timedelta(days=1), ["query"], 25000)
    seen = {r["keys"][0].strip().lower(): r for r in rows}
    def hit(q):
        r = seen.get(q.strip().lower())
        return (q, int(r["impressions"]), round(r["position"], 1)) if r else (q, 0, None)
    by_lang = {code: [hit(q) for q in t.get(code, [])] for code in LANG_NAME}
    rows = [x for code in LANG_NAME for x in by_lang[code]]
    out = {"total": len(rows), "shown": sum(1 for x in rows if x[1]), "rows": rows,
           "langs": {code: {"total": len(v), "shown": sum(1 for x in v if x[1])} for code, v in by_lang.items() if v}}
    ar = by_lang.get("ar", [])
    out.update(ar_total=len(ar), ar_shown=sum(1 for x in ar if x[1]))     # FNB's Arabic sub-metric reads these
    return out


def index_status(sess, paths):
    url = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
    # Time budget (Checkpoint 30d): on a newly added Search Console site each inspection can hang for a minute, which kept
    # the first A1 run in URL Inspection for over 15 minutes. Pages not reached in time are inspected on the next runs.
    budget = CFG.get("inspect_budget_s")
    deadline = time.monotonic() + budget if budget else None
    tries, wait_s = (2, 25) if budget else (3, 60)

    def ask(p):
        # Retries (19 Nov 2026): one read timeout used to drop the whole indexation reading for the run.
        err = None
        for attempt in range(tries):
            if deadline and time.monotonic() > deadline:
                break
            try:
                r = sess.post(url, json={"inspectionUrl": SITE + p, "siteUrl": SC_SITE}, timeout=wait_s)
            except Exception as e:
                err = "Search Console did not answer in time" if "Timeout" in type(e).__name__ else type(e).__name__
                time.sleep(3)
                continue
            if r.status_code == 200:
                st = r.json().get("inspectionResult", {}).get("indexStatusResult", {})
                return p, st.get("verdict") == "PASS", st.get("coverageState", "")
            err = f"URL Inspection {r.status_code}: {r.text[:160]}"
            if r.status_code in (401, 403):
                raise RuntimeError(err)
            time.sleep(3)
        raise RuntimeError(err or "URL Inspection failed")

    failed = []

    def one(p):
        if deadline and time.monotonic() > deadline:
            return p, None, None
        try:
            return ask(p)
        except RuntimeError as e:
            if " 401" in str(e) or " 403" in str(e):
                raise
            failed.append(str(e))
            return p, None, None
    # Incremental: indexed pages are rechecked once a day; the rest every run.
    cache_p = DATA / "index-cache.json"
    cache = json.loads(cache_p.read_text()) if cache_p.exists() else {}
    now = dt.datetime.now(dt.timezone.utc)
    def due(p):
        e = cache.get(p)
        if not e:
            return True
        age = (now - dt.datetime.fromisoformat(e["checked"])).total_seconds() / 3600
        return age >= (24 if e["indexed"] else CFG.get("recheck_hours", 0))
    todo = [p for p in paths if due(p)]
    # Larger sites (Checkpoint 30): a set number of inspections per run, never-checked pages first, then the oldest
    # readings, so the 2,000-a-day URL Inspection limit is never reached and every page is covered within a day or two.
    cap = CFG.get("inspect_per_run")
    if cap and len(todo) > cap:
        todo = sorted(todo, key=lambda p: (p in cache, cache.get(p, {}).get("checked", "")))[:cap]
    if todo:
        try:
            ask(todo[0])                # fail fast if not permitted, or (with a budget) if Google is not answering
        except RuntimeError as e:
            if " 401" in str(e) or " 403" in str(e) or (budget and "in time" in str(e)):
                raise
        with cf.ThreadPoolExecutor(4) as ex:
            for p, okk, cs in ex.map(one, todo):
                if okk is not None:     # a page that failed keeps its last reading
                    cache[p] = {"indexed": okk, "state": cs, "checked": now.isoformat(timespec="minutes")}
        if len(failed) == len(todo) and not any(p in cache for p in paths):
            raise RuntimeError(failed[0])
    cache = {p: cache[p] for p in paths if p in cache}
    cache_p.write_text(json.dumps(cache, ensure_ascii=False, indent=0))
    res = [(p, cache[p]["indexed"], cache[p]["state"]) for p in paths if p in cache]
    states = {}
    for _, _, cs in res:
        states[cs or "Unknown"] = states.get(cs or "Unknown", 0) + 1
    miss = {}
    for _, okk, cs in res:
        if not okk:
            miss[cs or "Unknown"] = miss.get(cs or "Unknown", 0) + 1
    return {"checked": len(res), "indexed": sum(1 for x in res if x[1]), "states": states, "rechecked_now": len(todo) - len(failed),
            "of": len(paths),
            "failed_now": len(failed),
            "not_states": miss, "not_indexed": [page_name(p) for p, okk, _ in res if not okk][:8]}


STATE_WORDS = {"URL is unknown to Google": "unknown to Google", "Discovered - currently not indexed": "found but not crawled yet",
               "Excluded by ‘noindex’ tag": "still marked noindex from an earlier Google visit",
               "Excluded by 'noindex' tag": "still marked noindex from an earlier Google visit",
               "Crawled - currently not indexed": "crawled but not indexed", "Unknown": "status not returned"}
pl = lambda k, w, s="s": f"{k} {w}{'' if k == 1 else s}"


def not_indexed_text(ix):
    st = ix.get("not_states") or {}
    return ", ".join(f"{v} {STATE_WORDS.get(k, k[:1].lower() + k[1:])}" for k, v in sorted(st.items(), key=lambda kv: -kv[1]))


def ai_sessions(sess):
    rows = ga(sess, TODAY - dt.timedelta(days=28), TODAY - dt.timedelta(days=1), ["sessionSource"], ["sessions"])
    src = {}
    for d, m in rows:
        if Q.AI_SOURCES.search(d[0]):
            src[d[0]] = src.get(d[0], 0) + m[0]
    return {"sessions": sum(src.values()), "sources": src}


def events_check(sess):
    rows = ga(sess, TODAY - dt.timedelta(days=28), TODAY, ["eventName"], ["eventCount"])
    out = {"counts": {d[0]: m[0] for d, m in rows}, "key": None}
    try:
        r = sess.get(f"https://analyticsadmin.googleapis.com/v1beta/properties/{GA_PROPERTY}/keyEvents", timeout=30)
        if r.status_code == 200:
            out["key"] = [k.get("eventName") for k in r.json().get("keyEvents", [])]
        else:
            out["key_err"] = f"{r.status_code}: {r.text[:160]}"
    except Exception as e:
        out["key_err"] = str(e)[:160]
    return out


# ---------------------------------------------------------------- Site crawl
class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title, self.in_title, self.desc, self.h1, self.canon, self.noindex = "", False, "", 0, "", False
        self.og, self.imgs, self.noalt, self.links, self.schema, self.lang = False, 0, 0, [], 0, ""
        self.res, self.viewport, self.alts, self.ld, self.in_ld = [], False, [], [], False

    def handle_starttag(self, tag, a):
        a = dict(a)
        if tag == "html":
            self.lang = a.get("lang", "")
        elif tag == "title":
            self.in_title = True
        elif tag == "meta":
            n, p = (a.get("name") or "").lower(), (a.get("property") or "").lower()
            if n == "description":
                self.desc = (a.get("content") or "").strip()
            if n == "robots" and "noindex" in (a.get("content") or "").lower():
                self.noindex = True
            if p == "og:image":
                self.og = True
            if n == "viewport":
                self.viewport = True
        elif tag == "h1":
            self.h1 += 1
        elif tag == "link":
            rel = (a.get("rel") or "").lower()
            if rel == "canonical":
                self.canon = a.get("href", "")
            if rel == "alternate" and a.get("hreflang") and a.get("href"):
                self.alts.append(a["href"])
            if rel in ("stylesheet", "preload", "icon") and a.get("href"):
                self.res.append(a["href"])
        elif tag == "img":
            self.imgs += 1
            if "alt" not in a:
                self.noalt += 1
            if a.get("src"):
                self.res.append(a["src"])
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag == "script":
            if a.get("type") == "application/ld+json":
                self.schema += 1
                self.in_ld = True
                self.ld.append("")
            if a.get("src"):
                self.res.append(a["src"])

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "script":
            self.in_ld = False

    def handle_data(self, d):
        if self.in_title:
            self.title += d
        if self.in_ld:
            self.ld[-1] += d


def _sameas(blocks):
    urls = set()
    for x in blocks:
        for m in re.finditer(r'"sameAs"\s*:\s*(\[[^\]]*\]|"[^"]*")', x):
            urls.update(re.findall(r'https?://[^"\s]+', m.group(1)))
    return len(urls)


def _json_ok(x):
    """A JSON-LD block counts only when it parses and every top-level object names its @context;
    without @context search engines do not read it as schema.org (Turkelite, 22 Nov 2026: a Blade
    template turned "@context" into PHP source text)."""
    try:
        j = json.loads(x)
    except Exception:
        return False
    items = j if isinstance(j, list) else [j]
    return bool(items) and all(isinstance(it, dict) and "schema.org" in str(it.get("@context", "")) for it in items)


# Pacing (18 Nov 2026): every request to the site goes through one shared limiter, so the crawl never sends more
# than about 3 requests a second however many threads run. Unpaced, six threads sent 20-25 a second and pushed the
# hosting account over its limit of 20 new database connections a second (17 Nov 21:19 and 18 Nov 03:07 UTC).
# The wait is taken before the timer starts, so the response times on the cards are unchanged.
PACE_S = max(0.0, float(os.environ.get("CRAWL_PACE_S", "0.45")))   # 0.35 until 24 Nov 2026
CRAWL_THREADS = 4   # 6 until 24 Nov 2026: Hostinger's CDN slowed the testing machine down on busy runs
_pace_lock = threading.Lock()
_next_at = [0.0]


def _pace():
    with _pace_lock:
        now = time.monotonic()
        wait = _next_at[0] - now
        _next_at[0] = max(now, _next_at[0]) + PACE_S
    if wait > 0:
        time.sleep(wait)


CONTROL_URL = os.environ.get("CONTROL_URL", "https://www.gstatic.com/generate_204")   # empty turns the check off (local tests)
CONTROL_LIMIT_MS = 400


def control_ms(n=5):
    """Median time for a tiny Google response from this machine. It tells a slow runner network from slow sites:
    on 23 Nov 2026 one run saw every page of all three sites take 2 to 6 s and a few time out, which scored as
    broken pages and zero page speed (23 Nov 2026)."""
    if not CONTROL_URL:
        return 0
    out = []
    for _ in range(n):
        t = time.perf_counter()
        try:
            requests.get(CONTROL_URL, timeout=10)
            out.append(round((time.perf_counter() - t) * 1000))
        except requests.RequestException:
            out.append(10000)
    out.sort()
    return out[len(out) // 2]


PSI_KEY = os.environ.get("PSI_KEY", "")


def psi_readings(sess=None):
    """Google PageSpeed Insights (mobile), measured from Google's servers, once a day per site, kept in psi.json.
    Hostinger's CDN can slow the testing machine down (23 Nov 2026: 27.7 s for a page that answered in 0.4 s in a
    browser), so the page speed score prefers Google's own reading. Works without a key at low volume; a PSI_KEY
    secret raises the quota. A failed day keeps the last good reading."""
    p = DATA / "psi.json"
    old = json.loads(p.read_text()) if p.exists() else {}
    now = dt.datetime.now(dt.timezone.utc)
    if old.get("pages") and old.get("at") and now - dt.datetime.fromisoformat(old["at"]) < dt.timedelta(hours=20):
        return old
    pages, err = {}, None
    for path in CFG.get("psi_pages") or [HOME]:
        try:
            # With a key, or else as the monitor's service account (its project's quota); keyless shares a
            # quota with everyone and was used up on 24 Nov 2026.
            getter = sess.get if sess is not None and not PSI_KEY else requests.get
            r = getter("https://www.googleapis.com/pagespeedonline/v5/runPagespeed", timeout=150,
                       params={"url": SITE + path, "strategy": "mobile", "category": "performance",
                               **({"key": PSI_KEY} if PSI_KEY else {})})
            j = r.json()
            if r.status_code != 200:
                err = ((j.get("error") or {}).get("message") or f"HTTP {r.status_code}")[:200]
                continue
            lr, au = j["lighthouseResult"], j["lighthouseResult"]["audits"]
            pages[path] = {"score": round(100 * (lr["categories"]["performance"]["score"] or 0)),
                           "lcp": round(au["largest-contentful-paint"]["numericValue"]),
                           "ttfb": round(au["server-response-time"]["numericValue"]),
                           "field": (j.get("loadingExperience") or {}).get("overall_category")}
        except Exception as e:
            err = str(e)[:200]
    if err:
        print(f"PageSpeed Insights: {err}", file=sys.stderr)
    if pages:
        out = {"at": now.isoformat(timespec="minutes"), "pages": pages, "error": err}
        p.write_text(json.dumps(out, ensure_ascii=False))
        return out
    return {**old, "error": err}


def fetch(url):
    for attempt in range(2):
        _pace()
        t = time.perf_counter()
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=30, allow_redirects=True)
        except requests.RequestException:
            if attempt == 0:
                time.sleep(3)   # a dropped or timed-out request gets one more try before it counts (23 Nov 2026)
                continue
            return None, round((time.perf_counter() - t) * 1000)
        ms = round((time.perf_counter() - t) * 1000)
        if r.status_code in (429, 503) and attempt == 0:
            time.sleep(5)   # the server asked us to slow down: wait, then try once more
            continue
        return r, ms


def crawl():
    sm, _ = fetch(SITE + "/sitemap.xml")
    smtext = sm.text if sm is not None else ""
    urls = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", smtext)
    lastmods = []
    for block in re.findall(r"<url>(.*?)</url>", smtext, re.S):
        m = re.search(r"<lastmod>\s*([0-9-]{10})", block)
        lastmods.append(m.group(1) if m else None)
    pages = {}

    def one(u):
        r, ms = fetch(u)
        o = {"u": urlparse(u).path or "/", "status": r.status_code if r is not None else 0, "ms": ms,
             "redir": bool(r is not None and r.history)}
        if r is not None and r.status_code == 200:
            p = Page()
            p.feed(r.text)
            o.update(Q.page_doc(r.text))
            o.update(title=p.title.strip(), desc=p.desc, h1=p.h1, canon=urlparse(p.canon).path if p.canon else "",
                     noindex=p.noindex or "noindex" in r.headers.get("X-Robots-Tag", "").lower(), og=p.og, imgs=p.imgs, noalt=p.noalt, schema=sum(1 for x in p.ld if _json_ok(x)), lang=p.lang,
                     links=sorted({urljoin(u, h).split("#")[0] for h in p.links if urljoin(u, h).startswith(SITE)}),
                     res=[urljoin(u, x) for x in p.res], kb=round(len(r.content) / 1024),
                     viewport=p.viewport, alts=sorted({urlparse(urljoin(u, x)).path for x in p.alts}),
                     sameas=_sameas(p.ld),
                     ld_bad=sum(1 for x in p.ld if not _json_ok(x)))
        return o

    with cf.ThreadPoolExecutor(CRAWL_THREADS) as ex:
        for o in ex.map(one, urls):
            pages[o["u"]] = o
    # Pages that did not answer at all get one more try, one at a time, before they count as not loading.
    for u in [u for u in urls if pages.get(urlparse(u).path or "/", {}).get("status") == 0][:50]:
        o = one(u)
        pages[o["u"]] = o
    # Linked pages outside the sitemap (fixed 19 Nov 2026): compare paths, not full links, so a link with a query
    # string to a listed page, or a link to a PDF, is not reported as a page missing from the sitemap. Every
    # unlisted link is still fetched once for the broken-link check.
    known = {urlparse(u).path.rstrip("/") or "/" for u in urls}

    def page_path(l):
        pr = urlparse(l)
        last = pr.path.rsplit("/", 1)[-1]
        return None if "." in last and not last.lower().endswith((".html", ".htm")) else (pr.path.rstrip("/") or "/")
    extra = sorted({l for o in pages.values() for l in o.get("links", []) if page_path(l) not in known or urlparse(l).query})

    def chk(u):
        r, _ = fetch(u)
        ni = bool(r is not None and r.status_code == 200 and ("noindex" in r.headers.get("X-Robots-Tag", "").lower() or
                  re.search(r"<meta[^>]+name=[\"']robots[\"'][^>]*noindex", r.text[:30000], re.I)))
        return u, ((r.status_code if r is not None else 0), bool(r is not None and r.history), ni)
    # Larger sites (Checkpoint 30c): a set number of unlisted links per run, never-checked ones first, then the oldest;
    # the rest keep their last reading from data/<site>/link-cache.json, so every link is covered over a few runs.
    cap = CFG.get("link_checks_per_run")
    lc_p = DATA / "link-cache.json"
    lcache = json.loads(lc_p.read_text()) if cap and lc_p.exists() else {}
    todo = extra if not cap or len(extra) <= cap else sorted(extra, key=lambda u: (u in lcache and lcache[u][1] != 0, lcache.get(u, ["", 0, 0, 0])[0]))[:cap]
    with cf.ThreadPoolExecutor(CRAWL_THREADS) as ex:
        fresh = dict(ex.map(chk, todo))
    linkfull = {u: tuple(lcache[u][1:]) for u in extra if u in lcache and u not in fresh}
    linkfull.update(fresh)
    if cap:
        stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
        # A link that did not answer at all is not kept, so the next run checks it again first (23 Nov 2026).
        lcache.update({u: [stamp, *v] for u, v in fresh.items() if v[0] != 0})
        lcache = {u: v for u, v in lcache.items() if v[1] != 0}
        lc_p.write_text(json.dumps({u: lcache[u] for u in extra if u in lcache}, ensure_ascii=False))
    linkres = {u: v[0] for u, v in linkfull.items()}
    missing = sorted({page_path(u) for u, (st, red, ni) in linkfull.items()
                      if st == 200 and not red and not ni and page_path(u) and page_path(u) not in known})
    ok = [o for o in pages.values() if o["status"] == 200]
    titles, descs = [o["title"] for o in ok], [o["desc"] for o in ok]
    issues = {
        "No share image": [o["u"] for o in ok if not o["og"]],
        "Description over 160 characters": [o["u"] for o in ok if len(o["desc"]) > 160],
        "Missing or duplicate title": [o["u"] for o in ok if not o["title"] or titles.count(o["title"]) > 1],
        "Missing or duplicate description": [o["u"] for o in ok if not o["desc"] or descs.count(o["desc"]) > 1],
        "Not exactly one main heading": [o["u"] for o in ok if o["h1"] != 1],
        "Canonical missing or wrong": [o["u"] for o in ok if not o["canon"] or o["canon"].rstrip("/") != o["u"].rstrip("/")],
        "Blocked from Google": [o["u"] for o in ok if o["noindex"]],
        "Images without alt text": [o["u"] for o in ok if o["noalt"]],
        "No structured data": [o["u"] for o in ok if not o["schema"]],
    }
    # Page size: each page plus every same-site file it references directly. Shared files are fetched once.
    def kind_of(u):
        last = urlparse(u).path.rsplit("/", 1)[-1].lower()
        ext = last.rsplit(".", 1)[-1] if "." in last else ""
        return "Fonts" if ext in ("woff2", "woff", "ttf", "otf") else "Styles" if ext == "css" else "Scripts" if ext in ("js", "mjs") else "Images"
    assets = sorted({u.split("#")[0] for o in ok for u in o["res"] if u.startswith(SITE)})

    def get_asset(u):
        r, _ = fetch(u)
        return u, (len(r.content) / 1024 if r is not None and r.status_code == 200 else None)
    with cf.ThreadPoolExecutor(CRAWL_THREADS) as ex:
        asize = dict(ex.map(get_asset, assets))

    def weigh(o):
        t = {"Page code": o["kb"], "Images": 0, "Scripts": 0, "Styles": 0, "Fonts": 0}
        files = []
        for u in sorted({x.split("#")[0] for x in o["res"] if x.startswith(SITE)}):
            kb = asize.get(u)
            if kb is None:
                continue
            k = kind_of(u)
            t[k] += kb
            files.append((urlparse(u).path.rsplit("/", 1)[-1] or u, k, kb))
        return t, files
    speed, site_t = [], {}
    for o in sorted(ok, key=lambda o: -o["ms"]):
        t, files = weigh(o)
        for k, v in t.items():
            site_t[k] = site_t.get(k, 0) + v
        speed.append({"name": page_name(o["u"]), "path": o["u"], "ms": o["ms"], "kb": round(sum(t.values())), "n": len(files) + 1,
                      "types": sorted(([k, round(v)] for k, v in t.items() if round(v) > 0), key=lambda x: -x[1]),
                      "files": [[n, k, round(kb)] for n, k, kb in sorted(files, key=lambda x: -x[2])[:4]]})
    uses = {}
    for o in ok:
        for u in {x.split("#")[0] for x in o["res"] if x.startswith(SITE)}:
            if asize.get(u):
                uses[u] = uses.get(u, 0) + 1
    big = max(uses, key=lambda u: asize[u] * uses[u], default=None)
    top_shared = [urlparse(big).path.rsplit("/", 1)[-1], kind_of(big), round(asize[big]), uses[big]] if big else None
    home = next((p for p in speed if (p["path"].rstrip("/") or "/") == (HOME.rstrip("/") or "/")), speed[0] if speed else None)
    weight = {k: v for k, v in home["types"]} if home else {}
    nfiles = home["n"] if home else 1
    site_types = sorted(([k, round(v / len(speed))] for k, v in site_t.items() if round(v / len(speed)) > 0), key=lambda x: -x[1]) if speed else []
    kbs = sorted(p["kb"] for p in speed)
    ms = sorted(o["ms"] for o in ok)
    inl = {}
    for o in ok:
        for l in o.get("links", []):
            pth = urlparse(l).path.rstrip("/") or "/"
            if pth != o["u"].rstrip("/"):
                inl[pth] = inl.get(pth, 0) + 1
    byp = {o["u"].rstrip("/"): o for o in ok}
    recip = [o for o in ok if o["alts"]]
    recip_ok = sum(1 for o in recip if all(o["u"].rstrip("/") in [x.rstrip("/") for x in byp.get(a.rstrip("/"), {}).get("alts", [])] or a.rstrip("/") == o["u"].rstrip("/") for a in o["alts"]))
    http, _ = fetch(SITE.replace("https://", "http://") + "/")
    robots, _ = fetch(SITE + "/robots.txt")
    llms, _ = fetch(SITE + "/llms.txt")
    rtext = robots.text if robots is not None and robots.status_code == 200 else ""
    import cube as cube_mod
    cfg = json.loads((DATA / "cube.json").read_text())
    ikey = str(cfg.get("indexnow_key") or "")
    ikr, _ = fetch(f"{SITE}/{ikey}.txt") if ikey else (None, None)
    tg = json.loads((DATA / "targets.json").read_text())
    try:
        q = Q.site_quality(ok, SITE, cfg, [x for code in LANG_NAME for x in tg.get(code, [])], lambda pth: cube_mod.path_allowed(rtext, "Googlebot", pth))
        (DATA / "pages.json").write_text(json.dumps({"date": iso(TODAY), "pages": Q.page_rows(ok)}, ensure_ascii=False, indent=0))
    except Exception as e:
        import traceback
        traceback.print_exc()
        q = {"error": str(e)[:200]}
    home_o = byp.get(HOME.rstrip("/") or "/") or (ok[0] if ok else {})
    ages = [(TODAY - dt.date.fromisoformat(x)).days for x in lastmods if x]
    slow = sorted(ok, key=lambda o: -o["ms"])[:5]
    return {
        "date": iso(TODAY),
        "pages": len(pages), "pages_ok": len(ok),
        "lang": {LANG_NAME[code]: sum(1 for o in ok if siteconf.lang_of(o["lang"]) == code) for code in LANG_NAME},
        "redirects": sum(1 for o in pages.values() if o["redir"]), "errors": len(pages) - len(ok),
        "extra_links": len(extra), "links_unchecked": len(extra) - len(linkfull), "broken": [u for u, s in linkres.items() if s != 200] + [o["u"] for o in pages.values() if o["status"] != 200],
        "issues": {k: v for k, v in issues.items()}, "issue_pages": len({u for v in issues.values() for u in v}),
        "ms_median": ms[len(ms) // 2] if ms else None, "ms_max": ms[-1] if ms else None,
        "slowest": [[page_name(o["u"]), o["ms"]] for o in slow],
        "weight": weight, "weight_total": sum(weight.values()), "files": nfiles,
        "speed_pages": speed, "site_types": site_types, "top_shared": top_shared, "kb_median": kbs[len(kbs) // 2] if kbs else None,
        "missing_from_sitemap": missing,
        "q": q, "noindex": [o["u"] for o in ok if o["noindex"]],
        "robots_ok": bool(robots is not None and robots.status_code == 200),
        "robots_sitemap": bool(re.search(r"(?im)^\s*sitemap\s*:", rtext)),
        "lastmod_share": round(sum(1 for x in lastmods if x) / len(lastmods), 3) if lastmods else 0,
        "lastmod_age_median": sorted(ages)[len(ages) // 2] if ages else None,
        "inlinks_ge3": sum(1 for o in ok if inl.get(o["u"].rstrip("/") or "/", 0) >= 3),
        "weak_pages": [[page_name(o["u"]), inl.get(o["u"].rstrip("/") or "/", 0)] for o in sorted(ok, key=lambda o: inl.get(o["u"].rstrip("/") or "/", 0))[:6]],
        "hreflang_pages": len(recip), "hreflang_ok": recip_ok,
        "viewport_share": round(sum(1 for o in ok if o["viewport"]) / len(ok), 3) if ok else 0,
        "https_redirect": bool(http is not None and http.url.startswith("https://")),
        "robots": rtext,
        "llms_txt": bool(llms is not None and llms.status_code == 200 and len(llms.text) > 50),
        "indexnow_key_ok": bool(ikey and ikr is not None and ikr.status_code == 200 and ikr.text.strip() == ikey),
        "sameas_home": home_o.get("sameas", 0), "ld_bad": sum(o.get("ld_bad", 0) for o in ok),
        "n_ok": len(ok),
        "pass": {
            "titles": sum(1 for o in ok if o["title"] and titles.count(o["title"]) == 1 and 25 <= len(o["title"]) <= 65),
            "meta": sum(1 for o in ok if o["desc"] and descs.count(o["desc"]) == 1 and 70 <= len(o["desc"]) <= 160),
            "h1": sum(1 for o in ok if o["h1"] == 1),
            "canon": sum(1 for o in ok if o["canon"] and o["canon"].rstrip("/") == o["u"].rstrip("/")),
            "alt": sum(1 for o in ok if not o["noalt"] and o["og"]),
            "schema": sum(1 for o in ok if o["schema"]),
        },
        "urls": [o["u"] for o in ok],
    }


def history(days=14):
    out = {}
    for p in sorted(HIST.glob("*.json"))[-days:]:
        try:
            out[p.stem] = json.loads(p.read_text())
        except Exception:
            pass
    return out


def crawl_cards(c, hist):
    dates = sorted(hist)[-7:]
    v = lambda k: [hist[d].get("crawl", {}).get(k) for d in dates]
    sub = f"{CR}, read {short(TODAY)}"
    once = ["One reading a day; the line fills in as the snapshot repeats."]
    iss = sorted(((k, len(u)) for k, u in c["issues"].items()), key=lambda x: -x[1])
    cards = [
        reading("pages", "Pages live", "Pages live", "pages", "Site health", CR, "sitemap.xml URLs, HTTP status of each",
                dates, v("pages_ok"), sub,
                [("By language", list(c["lang"].items()), "How many pages in each language?", "Language", "Pages"),
                 ("By response", [("Loads normally (200)", c["pages_ok"]), ("Redirects", c["redirects"]), ("Errors", c["errors"])], "Do all pages load?", "Response", "Pages")],
                None, "Every address in the sitemap is requested once; a page counts as live when it answers with status 200.",
                ["Pages not in the sitemap are only found if another page links to them."] + once,
                pats=[{"type": "movement", "title": f"{c['pages_ok']} of {c['pages']} sitemap pages load",
                       "evidence": ", ".join(f"{v} {k}" for k, v in c['lang'].items()) + f"; {c['errors']} errors."}]),
        reading("broken", "Broken links", "Broken links", "links", "Site health", CR, "every internal link on every page, HTTP status",
                dates, v("broken_n"), sub,
                [("Addresses checked", [("Sitemap pages", c["pages"]), ("Other linked pages", c["extra_links"])], "How many addresses were checked?", "Group", "Addresses"),
                 ("Broken addresses", [(u.replace(SITE, ""), 1) for u in c["broken"][:8]] or [("None", 0)], "Which links are broken?", "Address", "Count")],
                None, "Every internal link found on the sitemap pages is requested once; a link is broken when it does not answer with status 200.",
                ["Links to other websites are not tested."] + once, lower_better=True),
        reading("issues", "Pages with issues", "Pages with issues", "pages", "Site health", CR,
                "title, meta description, h1, canonical, robots, alt text, structured data, share image per page",
                dates, v("issue_pages"), sub,
                [("By issue", iss, "Which issues were found?", "Issue", "Pages")],
                None, "Each sitemap page is tested against nine checks; a page counts once however many checks it fails.",
                ["Checks cover the page code, not how Google has indexed it."] + once, lower_better=True),
    ]
    cards.append(speed_card(c, hist, dates, v, sub, once))
    return cards


RUNS = DATA / "runs.json"
CRAWL_KEYS = ("pages_ok", "broken_n", "issue_pages", "ms_median", "weight_total")


def crawl_windows(cards, hist_all, runs):
    """Site checks by window: 12 and 24 hours use each 3-hourly run; 30 days and since launch use one reading a day."""
    by = {x["id"]: x for x in cards}
    now = dt.datetime.now(dt.timezone.utc)
    spec = {"pages": ("pages_ok", False), "broken": ("broken_n", True), "issues": ("issue_pages", True), "speed": ("ms_median", True)}
    for wkey in ("12h", "24h", "30d", "all"):
        if wkey in ("12h", "24h"):
            since = now - dt.timedelta(hours=WIN[wkey]["n"])
            rs = [r for r in runs if dt.datetime.strptime(r["t"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=dt.timezone.utc) > since]
            if not rs:
                continue
            dates = [r["t"] for r in rs]
            val = lambda k: [r.get(k) for r in rs]
            heading, once = "Check by check", [f"One reading per check, about every 3 hours; {len(rs)} checks in the last {WIN[wkey]['span']}."]
        else:
            ds = [d for d in sorted(hist_all) if hist_all[d].get("crawl") and d >= iso(LAUNCH)]
            if wkey == "30d":
                ds = ds[-30:]
            if not ds:
                continue
            dates = ds
            val = lambda k: [hist_all[d]["crawl"].get(k) for d in ds]
            heading, once = "Day by day", ["One reading a day, the last check of the day."]
        span = span_label(dates, wkey)
        for cid, (k, lower) in spec.items():
            base = by.get(cid)
            if not base or not any(v is not None for v in val(k)):
                continue
            src_q = next((q for q in base["questions"] if q["id"] == "source"), None)
            cav = next((q["answer"]["items"] for q in base["questions"] if q["id"] == "caveats"), [])
            b = reading(cid, base["label"], base["short"], base["unit"], base["group"], CR,
                        src_q["answer"]["rows"][0][1] if src_q else "", dates, val(k), f"{CR}, {span}",
                        [(x["title"], [(r["label"], r["value"]) for r in x["rows"]], x["title"], "Item", base["unit"]) for x in base["breakdowns"]],
                        None, base["howCalculated"], [x for x in cav if not x.startswith("One reading")] + once,
                        heading=heading, lower_better=lower)
            b["win"], b["periodLabel"] = wkey, span
            b["main"]["bucket"] = "check" if wkey in ("12h", "24h") else "day"
            for extra in ("pages", "kpis"):
                if extra in base:
                    b[extra] = base[extra]
            attach(base, wkey, b)


def speed_card(c, hist, dates, v, sub, once):
    """Page speed: median response time, with every page listed slowest first and its size by file type."""
    sp, st = c["speed_pages"], c["site_types"]
    stot = sum(x[1] for x in st) or 1
    home = next((p for p in sp if (p["path"].rstrip("/") or "/") == (HOME.rstrip("/") or "/")), None)
    over = [p for p in sp if p["ms"] >= 1000]
    w = [(d, x) for d, x in zip(dates, v("weight_total")) if x is not None]
    wd = w[-1][1] - w[-2][1] if len(w) > 1 else None
    wnote = ("First reading" if wd is None else ("Level with " if wd == 0 else f"{'+' if wd > 0 else '−'}{f(abs(wd))} KB on ")
             + short(dt.date.fromisoformat(w[-2][0]))) if w else ""
    card_ = reading("speed", "Page speed", "Page speed, ms", "ms", "Site health", CR,
                    "time to fetch each page; size of each page and the same-site files it references",
                    dates, v("ms_median"), sub,
                    [("Average page by file type, KB", st, "What makes up an average page?", "Type", "KB"),
                     ("Slowest pages, ms", [(p["name"], p["ms"]) for p in sp[:6]], "Which pages are slowest?", "Page", "ms")],
                    None, "Median time to download the page code across the sitemap pages, in milliseconds. "
                          "Page size is the page code plus every file on the site it references directly.",
                    [f"Measured from a GitHub server in the United States; visitors in {MARKET['the']} will see different times, and the host's network sometimes slows such servers down.",
                     "Response time is the page code only; images, scripts, styles and fonts load after it.",
                     "Uncompressed sizes; the transfer over the network is smaller. A file shared by many pages counts on each page.",
                     "Google Analytics, which loads after cookies are accepted, is not included."] + once, lower_better=True)
    card_["pages"] = sp
    card_["kpis"] = [
        {"label": "Slowest page", "value": f"{f(sp[0]['ms'])} ms" if sp else "--", "note": sp[0]["name"] if sp else "",
         "tone": "down" if sp and sp[0]["ms"] >= 1000 else ""},
        {"label": "Over 1 second", "value": f"{len(over)} pages", "note": f"of {len(sp)}", "tone": "down" if over else "up"},
        {"label": "Home page", "value": f"{f(home['kb'])} KB" if home else "--", "note": wnote,
         "tone": "down" if wd and wd > 0 else "up" if wd and wd < 0 else ""},
        {"label": "Heaviest type", "value": st[0][0] if st else "--",
         "note": f"{round(100 * st[0][1] / stot)}% of an average page" if st else ""}]
    if sp:
        card_["patterns"].append({"type": "peak", "title": f"Slowest page: {sp[0]['name']}",
                                  "evidence": f"{f(sp[0]['ms'])} ms; {f(sp[0]['kb'])} KB, mostly {sp[0]['types'][0][0].lower()}." if sp[0]["types"] else f"{f(sp[0]['ms'])} ms."})
    if st:
        card_["patterns"].append({"type": "concentration", "title": f"{st[0][0]} are {round(100 * st[0][1] / stot)}% of an average page",
                                  "evidence": f"{f(st[0][1])} of {f(stot)} KB; median page size {f(c['kb_median'])} KB."})
    return card_


def semrush_cards():
    p = DATA / "semrush.json"
    if not p.exists():
        return []
    s = json.loads(p.read_text())
    m = s["monthly"]
    dates = [r["date"] for r in m]
    sub = f"{SM}, monthly, read {s['read']}"
    return [
        reading("refdomains", "Referring domains", "Referring domains", "domains", "Authority", SM,
                "backlinks_historical: domains_num; backlinks_refdomains", dates, [r["domains"] for r in m], sub,
                [("Highest authority score among them", [tuple(x) for x in s["top_domains"]], "Which linking sites carry most authority?", "Domain", "Authority score"),
                 ("Backlinks by type", [("Follow", s["follow"]), ("Nofollow", s["nofollow"])], "How many links pass authority?", "Type", "Backlinks")],
                s.get("next_domains"), f"Websites with at least one link to {HOSTS[0]}, counted by Semrush each month. {s['backlinks']} backlinks in total.",
                ["Refreshed by hand during working sessions, not daily.", "Semrush finds links by its own crawl, so new links appear with a delay."],
                heading="Month by month", pats=s.get("patterns_domains")),
        reading("authority", "Authority score", "Authority score, of 100", "points", "Authority", SM,
                "backlinks_overview: authority_score", dates, [r["score"] for r in m], sub,
                [("What Semrush sees", [("Referring domains", m[-1]["domains"]), ("Backlinks", s["backlinks"]), (f"Keywords ranking in {s.get('market_label', 'the UAE')}", s.get("market_keywords", s.get("uae_keywords", 0)))], "What is the score built on?", "Measure", "Count")],
                s.get("next_score"), "Semrush Authority Score for the domain, 0 to 100, from link quality, search traffic and spam signals.",
                ["A third-party estimate, not a Google number.", "Refreshed by hand during working sessions, not daily."],
                heading="Month by month", pats=s.get("patterns_score")),
    ]


# ---------------------------------------------------------------- Cube card
CARD_NAMES = {"pages": "Site health, Pages live", "broken": "Site health, Broken links", "speed": "Site health, Page speed", "issues": "Site health, Pages with issues", "refdomains": "Authority, Referring domains",
              "authority": "Authority, Authority score", "impressions": "Google Search, Search impressions", "pageone": "Google Search, Keywords on page one",
              **{q["id"]: f"Enquiries, {q['label']}" for q in ENQ}}


def band(score, target):
    return "good" if score >= target - 0.05 else "warn" if score >= target - 1.5 else "bad"


def cube_card(cs, cube, hist, g):
    audit_day = cube["audit_date"]
    AL = cube.get("audit_label", "Audit")                       # "Audit" for FNB, "Baseline" for sites without a manual audit
    AD = f"{short(dt.date.fromisoformat(audit_day))} {AL.lower()}"
    AW = AL.lower()
    all_days = [d for d in sorted(hist) if hist[d].get("cube")][-63:]   # heatmap: rolling history, 7 days in view
    days = all_days[-7:]
    # The audit (or baseline) column is keyed "audit", not by its date: a new site's baseline day is also its first
    # history day, and both columns used to show the baseline (Checkpoint 30f).
    cols = (["audit"] if audit_day not in days else []) + days          # charts and popups: audit plus the last 7
    hcols = ["audit"] + all_days
    dt_of = lambda d: audit_day if d == "audit" else d
    colname = [AL] + [short(dt.date.fromisoformat(d)) for d in all_days]
    import cube as cube_mod
    group = {b["id"]: b["group"] for b in cube["blocks"]}
    def tgt(d, bid):   # target of the stage that day was in
        return cube["target_groups"][group[bid]][cube_mod.stage_of(cube, dt.date.fromisoformat(dt_of(d)))[0]]
    def val(d, bid=None):
        if d == "audit":
            return cube["audit_overall"] if bid is None else next(b["audit"] for b in cs["blocks"] if b["id"] == bid)
        h = hist[d]["cube"]
        return h["overall"] if bid is None else h["blocks"].get(bid)
    lost = lambda b: max(0.0, b["target"] - b["score"]) * b["weight"] / 100
    order = sorted(cs["blocks"], key=lambda b: (-lost(b), -b["weight"]))
    rows = [{"id": b["id"], "name": b["name"], "weight": b["weight"], "target": b["target"],
             "cells": [val(d, b["id"]) for d in hcols],
             "bands": [band(val(d, b["id"]) or 0, tgt(d, b["id"])) for d in hcols],
             "targets": [tgt(d, b["id"]) for d in hcols],
             "subs": [{"name": x_["name"], "weight": x_["weight"], "score": x_["score"], "audit": x_["audit"],
                       "band": band(x_["score"], b["target"]), "measured": x_["measured"],
                       "evidence": x_["evidence_now"]} for x_ in b["subs"]]} for b in order]
    day_n = (TODAY - LAUNCH).days + 1
    stage_note = f"{cs['stage']} stage, day {day_n}" + (f", to {short(dt.date.fromisoformat(cs['stage_until']))}" if cs["stage_until"] else "")
    on = sum(1 for b in cs["blocks"] if band(b["score"], b["target"]) == "good")
    tot, aud = cs["overall"], cube["audit_overall"]
    x = round(tot - aud, 2)

    def block_obj(b):
        hist_vals = [val(d, b["id"]) for d in cols]
        subs = sorted(b["subs"], key=lambda x_: -(max(0, b["target"] - x_["score"]) * x_["weight"]))
        worst = subs[0]
        measured_n = sum(1 for x_ in b["subs"] if x_["measured"])
        part_n = sum(1 for x_ in b["subs"] if x_["measured"] and x_["part"] < 1)
        q = [{"intent": "status", "id": "total", "text": "What is the score?",
              "answer": {"type": "stat", "value": f"{b['score']:.1f}", "label": f"{b['name']}, of 10",
                         "sub": f"Target {b['target']:.1f} at the {cs['stage']} stage; {AW} {b['audit']:.1f}"}},
             {"intent": "source", "id": "subs", "text": "What is it made of?",
              "answer": {"type": "table", "columns": ["Sub-metric", "Weight", "Score", "Source"],
                         "rows": [[x_["name"], f"{x_['weight']}%", f"{x_['score']:.1f}", x_["source"]] for x_ in b["subs"]], "note": ""}},
             {"intent": "next", "id": "next", "text": "What should we work on first?",
              "answer": {"type": "table", "columns": ["Sub-metric", "Why"],
                         "rows": [[x_["name"], x_["evidence_now"] or f"Scored in the {AD}."] for x_ in subs[:3]], "note": ""}},
             {"intent": "trust", "id": "how", "text": "How is it scored?",
              "answer": {"type": "list", "items": [
                  f"{measured_n} of {len(b['subs'])} sub-metrics are measured" + (f", {part_n} of them in part" if part_n else "")
                  + "; " + (f"the rest keep the {AD} score until reviewed." if measured_n < len(b["subs"]) else f"none rest on the {AW} alone.")
                  + (f" A part-measured score blends the rule with the {AW}, as its source shows." if part_n else ""),
                  "The block score is the weighted mean of its sub-metrics, 0 to 10.",
                  "Measured sub-metrics use a fixed rule (shown under each one), so they can differ from the audit's judgement on the first day."
                  if AW == "audit" else "The baseline is the first day's measured readings; sub-metrics that cannot be measured carry a judged score."]}}]
        if b["cards"]:
            q.append({"intent": "source", "id": "cards", "text": "Which cards show the detail?",
                      "answer": {"type": "list", "items": [CARD_NAMES.get(c_, c_) for c_ in b["cards"]]}})
        return {"id": "block-" + b["id"], "available": True, "brand": K, "period": len(cols),
                "periodLabel": stage_note, "label": b["name"], "unit": "points", "through": dt_of(cols[-1]),
                "stats": {"total": round(b["score"], 1), "previousTotal": b["audit"], "change": None,
                          "deltaText": f"Target {b['target']:.1f}, " + ("on target" if band(b["score"], b["target"]) == "good" else f"{b['target'] - b['score']:.1f} below"),
                          "deltaTone": "up" if band(b["score"], b["target"]) == "good" else "down"},
                "health": [{"site": SITE_NAME, "statusLabel": "Live", "through": dt_of(cols[-1]), "via": "Cube"}],
                "main": {"dates": [dt_of(d) for d in cols], "heading": "Score by snapshot", "previousLabel": "the stage target",
                         "series": {K: [{"date": dt_of(d), "value": v} for d, v in zip(cols, hist_vals)]},
                         "previous": [{"date": dt_of(d), "value": b["target"]} for d in cols], "tipLabel": "Stage target"},
                "breakdowns": [{"id": "subs", "title": "Sub-metrics, score of 10",
                                "rows": [{"label": x_["name"], "value": round(x_["score"], 1)} for x_ in b["subs"]]}],
                "patterns": [{"type": "gap", "title": f"Weakest: {worst['name']} at {worst['score']:.1f}",
                              "evidence": worst["evidence_now"] or f"Scored in the {AD}."}]
                            + [{"type": "caution", "title": "Partly measured", "evidence": f"{len(b['subs']) - measured_n} of {len(b['subs'])} sub-metrics still carry the {AW} score."}] * (measured_n < len(b["subs"])),
                "questions": q,
                "raw": {"columns": ["Sub-metric", "Weight", "Score", "Source", "Evidence"],
                        "rows": [[x_["name"], x_["weight"], x_["score"], x_["source"], x_["evidence_now"]] for x_ in b["subs"]]},
                "howCalculated": "Weighted mean of the sub-metrics. Colour compares the score with the target for the current stage: on target, within 1.5 points, or further below."}

    gaps = sorted(cs["blocks"], key=lambda b: -lost(b))
    pats = [{"type": "movement", "title": f"{on} of {len(cs['blocks'])} blocks on target for the {cs['stage']} stage",
             "evidence": f"Overall {tot:.2f} against a stage target of {cs['target']:.2f}; the {AD} scored {aud:.2f}."}]
    if lost(gaps[0]) > 0:
        pats.append({"type": "gap", "title": f"Most points lost: {gaps[0]['name']}",
                     "evidence": f"{gaps[0]['score']:.1f} against {gaps[0]['target']:.1f}, worth {lost(gaps[0]):.2f} of the overall score."})
    if SID == "fnb" and TODAY <= dt.date(2026, 12, 19):
        pats.append({"type": "caution", "title": "Wider measurement from Nov 19",
                     "evidence": "Twenty more sub-metrics moved from the Nov 13 audit to fixed daily rules on Nov 19 (40 of 45 now), "
                                 "so scores before and after that day are not like for like."})
    pats.append({"type": "caution", "title": "New site, warm-up period",
                 "evidence": f"The site went live on {short(LAUNCH)}. Indexation and search presence usually take two to four weeks to settle; off-site blocks build over months."})
    q = [{"intent": "status", "id": "total", "text": "What is the overall score?",
          "answer": {"type": "stat", "value": f"{tot:.2f}", "label": "Search visibility, of 10",
                     "sub": f"Stage target {cs['target']:.2f}; {AW} {aud:.2f}"}},
         {"intent": "status", "id": "blocks", "text": "How does each block stand?",
          "answer": {"type": "table", "columns": ["Block", "Weight", "Score", "Target"],
                     "rows": [[b["name"], f"{b['weight']}%", f"{b['score']:.1f}", f"{b['target']:.1f}"] for b in order], "note": ""}},
         {"intent": "next", "id": "next", "text": "Where are the biggest gains?",
          "answer": {"type": "table", "columns": ["Block", "Points to gain overall"],
                     "rows": [[b["name"], f"+{lost(b):.2f}"] for b in gaps if lost(b) > 0][:5], "note": ""}},
         {"intent": "trust", "id": "how", "text": "How are the targets set?",
          "answer": {"type": "table", "columns": ["Stage", "Until", "On-site", "Content", "Entity and local", "Off-site, AI answers"],
                     "rows": [[st["name"], short(dt.date.fromisoformat(st["until"])) if st["until"] else "After",
                               *[f"{cube['target_groups'][k][i]:.1f}" for k in ("onsite", "content", "entity", "offsite")]]
                              for i, st in enumerate(cube["stages"])], "note": f"Stages are 7-day spans from the launch on {short(LAUNCH)}."}}]
    if g.get("targets"):
        q.insert(3, {"intent": "source", "id": "targets", "text": "Which target searches show the site?",
                     "answer": {"type": "table", "columns": ["Search", "Impressions, 28 days", "Position"],
                                "rows": [[r[0], f(r[1]), "-" if r[2] is None else f"{r[2]:.1f}"] for r in g["targets"]["rows"]], "note": f"Edit the list in {(DATA / 'targets.json').relative_to(ROOT)}."}})
    unk = (g.get("index") or {}).get("checked", 0) - (g.get("index") or {}).get("indexed", 0)
    eo = len(((CRAWL.get("q") or {}).get("parity") or {}).get("en_only") or [])
    ctx = {"missing_pages": pl(len(CRAWL.get("missing_from_sitemap", [])), "linked page"), "unknown_pages": pl(unk, "page"),
           "slowest": "; ".join(x_[0] for x_ in CRAWL.get("slowest", [])[:2]), "noshare_pages": pl(len(CRAWL.get("issues", {}).get("No share image", [])), "page"),
           "en_only_pages": pl(eo, "English page"), "noindex_pages": pl(len(CRAWL.get("noindex", [])), "noindex page"),
           **{f"en_only_pages_{x['code']}": pl(len((((CRAWL.get("q") or {}).get("lang") or {}).get(x["code"]) or {}).get("en_only") or []), f"{LANG_NAME[MAIN_LANG]} page")
              for x in OTHER_LANGS}}
    acts = {(b["id"], x_["name"]): (x_.get("action", "").format(**ctx), x_.get("owner", "site")) for b in cs["blocks"] for x_ in b["subs"]}
    for r in rows:
        for x_ in r["subs"]:
            x_["action"], x_["owner"] = acts.get((r["id"], x_["name"]), ("", "site"))
    gains = []
    for b in cs["blocks"]:
        for x_ in b["subs"]:
            gain = b["weight"] * x_["weight"] * max(0.0, b["target"] - x_["score"]) / 10000
            # An action whose count came out as zero (its reading was missing this run) is left out, not shown as "the 0 pages".
            if gain >= 0.005 and x_.get("action") and not re.search(r"\bthe 0 \w", x_["action"].format(**ctx)):
                gains.append((gain, b, x_))
    gains.sort(key=lambda t: -t[0])
    nxt = [{"t": x_["action"].format(**ctx), "why": f"{b['name']}: {x_['name']} at {x_['score']:.1f}, block target {b['target']:.1f}.",
            "gain": round(gain, 2), "owner": x_.get("owner", "site"), "impact": "high" if gain >= 0.1 else "med" if gain >= 0.04 else "low"}
           for gain, b, x_ in gains[:6]]
    n_meas = sum(1 for b in cs["blocks"] for x_ in b["subs"] if x_["measured"])
    n_all = sum(len(b["subs"]) for b in cs["blocks"])
    left = (dt.date.fromisoformat(cs["stage_until"]) - TODAY).days if cs["stage_until"] else None
    kpis = [{"label": "Stage target", "value": f"{cs['target']:.2f}", "note": f"{cs['target'] - tot:.2f} to go" if tot < cs["target"] else "Reached", "tone": "down" if tot < cs["target"] else "up"},
            {"label": "Blocks on target", "value": f"{on} of {len(cs['blocks'])}"},
            {"label": "Measured live", "value": f"{n_meas} of {n_all}"},
            {"label": "Stage ends", "value": short(dt.date.fromisoformat(cs["stage_until"])) if left is not None else "-", "note": f"{left} days left" if left is not None else ""}]
    return {"id": "cube", "group": "Overview", "kind": "heatmap", "next": nxt, "kpis": kpis, "status": "live", "source": "Cube", "short": "Search visibility",
            "level": True, "sub": stage_note, "available": True, "brand": K,
            "period": len(cols), "periodLabel": stage_note, "label": "Search visibility", "unit": "points", "through": dt_of(cols[-1]),
            "stats": {"total": round(tot, 2), "previousTotal": aud, "change": None,
                      "deltaText": ("Level with" if x == 0 else f"{'+' if x > 0 else '−'}{abs(x):.2f} on") + f" the {AD}",
                      "deltaTone": "up" if x > 0 else "down" if x < 0 else "",
                      "railText": "level" if x == 0 else f"{'+' if x > 0 else '−'}{abs(x):.2f}", "railTone": "up" if x > 0 else "down" if x < 0 else ""},
            "heat": {"cols": colname, "dates": [dt_of(d) for d in hcols], "stages": cube["stages"], "rows": rows, "stage": cs["stage"], "target": cs["target"],
                     "auditLabel": f"{AL}, {short(dt.date.fromisoformat(audit_day))}"},
            "blocks": {b["id"]: block_obj(b) for b in cs["blocks"]},
            "health": [{"site": SITE_NAME, "statusLabel": "Live", "through": dt_of(cols[-1]), "via": "Cube"}],
            "main": {"dates": [dt_of(d) for d in cols], "heading": "Overall score by snapshot", "previousLabel": "the stage target",
                     "series": {K: [{"date": dt_of(d), "value": val(d)} for d in cols]},
                     "previous": [{"date": dt_of(d), "value": cs["target"]} for d in cols], "tipLabel": "Stage target"},
            "breakdowns": [{"id": "gain", "title": "Points to gain, by block", "rows": [{"label": b["name"], "value": round(lost(b), 2)} for b in gaps if lost(b) > 0]}]
                          + ([{"id": "index", "title": "Pages in Google's index", "rows": [{"label": {"Submitted and indexed": "Indexed"}.get(k, k.replace("‘", "").replace("’", "")), "value": v} for k, v in sorted(g["index"]["states"].items(), key=lambda kv: -kv[1])]}] if g.get("index") else [])
                          + ([{"id": "targets", "title": f"Target searches showing, {g['targets']['shown']} of {g['targets']['total']}", "rows": [{"label": r[0], "value": r[1]} for r in sorted(g["targets"]["rows"], key=lambda r: -r[1])[:5]]}] if g.get("targets") else [])
                          + [{"id": "blocks", "title": "Blocks, score of 10", "rows": [{"label": b["name"], "value": round(b["score"], 1)} for b in order]}],
            "patterns": pats, "questions": q,
            "raw": {"columns": ["Block", "Weight", "Score", "Target", "Audit"],
                    "rows": [[b["name"], b["weight"], b["score"], b["target"], b["audit"]] for b in order]},
            "howCalculated": f"Ten blocks with fixed weights, each the weighted mean of its sub-metrics, 0 to 10. The overall score is the weighted sum. Targets follow the stage counted from the {short(LAUNCH)} launch; in the heatmap each day is coloured against the target of its own stage."}


def cube_windows(cc):
    """Search visibility by window: 7 days as day columns (the card itself), 30 days as a strip of day cells,
    since launch as one column per week, each week's average against its stage target."""
    h = cc["heat"]
    attach(cc, "30d", {"win": "30d", "heat": {**h, "mode": "dense", "inview": 30,
                                               "note": "each cell is a day against its stage target"},
                       "periodLabel": cc["periodLabel"]})
    dates = h["dates"][1:]
    launch_iso = iso(LAUNCH)
    days = [d for d in dates if d >= launch_iso]
    if not days:
        return
    weeks = sorted({(dt.date.fromisoformat(d) - LAUNCH).days // 7 for d in days})
    wk0 = [LAUNCH + dt.timedelta(days=7 * w) for w in weeks]
    rows = []
    for r in h["rows"]:
        cells, bands, tgts = [r["cells"][0]], [r["bands"][0]], [r["targets"][0]]
        for w, d0 in zip(weeks, wk0):
            idx = [i + 1 for i, d in enumerate(dates) if d >= launch_iso and (dt.date.fromisoformat(d) - LAUNCH).days // 7 == w]
            vals = [r["cells"][i] for i in idx if r["cells"][i] is not None]
            v = round(sum(vals) / len(vals), 2) if vals else None
            t = r["targets"][idx[-1]] if idx else r["target"]
            cells.append(v)
            tgts.append(t)
            bands.append(band(v or 0, t))
        rows.append({**r, "cells": cells, "bands": bands, "targets": tgts})
    end = lambda d0: min(d0 + dt.timedelta(days=6), TODAY)
    attach(cc, "all", {"win": "all", "periodLabel": f"Since {short(LAUNCH)}, by week",
                       "heat": {**h, "mode": "weeks", "inview": 4, "step": 7,
                                "note": "each week's average against its stage target",
                                "cols": ["Audit"] + [f"{short(d0)}" for d0 in wk0],
                                "spans": [""] + [f"{short(d0)} to {short(end(d0))}" for d0 in wk0],
                                "dates": [h["dates"][0]] + [iso(d0) for d0 in wk0], "rows": rows}})


# ---------------------------------------------------------------- Next steps for each card
def step(t, why, impact="med", owner="site"):
    return {"t": t, "why": why, "impact": impact, "owner": owner}


def next_steps(cards, c, g):
    by = {x["id"]: x for x in cards}
    tot = lambda i: by[i]["stats"]["total"] if i in by else None
    top_row = lambda i, n=0: (by[i]["breakdowns"][n]["rows"][0] if i in by and len(by[i]["breakdowns"]) > n and by[i]["breakdowns"][n]["rows"] else None)
    ix = g.get("index") or {}
    unknown = ix.get("checked", 0) - ix.get("indexed", 0)
    q = c.get("q") or {}
    rules = {}
    for qd in ENQ:                       # enquiry cards, from sites/<id>.json
        cid, n_ = qd["id"], tot(qd["id"])
        if cid not in by:
            continue
        if not n_:
            rules[cid] = [step(qd["test"], f"No {qd['unit']} recorded this week.", "high" if qd.get("kind") in ("lead", "tool") else "med", "owner")]
            if qd.get("kind") == "lead":
                rules[cid].append(step("Mark generate_lead as a key event in Google Analytics.", "", "med", "owner"))
            if qd.get("kind") == "tool":
                rules[cid].append(step("Register the tool parameter as a custom dimension in Analytics.", "", "med", "owner"))
        elif qd.get("kind") == "lead":
            rules[cid] = [step("Reply to every request within the hour and note the outcome.", f"{pl(n_, qd['one'])} this week.", "high", "owner")]
        elif qd.get("kind") == "tool":
            rules[cid] = [step(f"Feature {top_row(cid)['label'] if top_row(cid) else 'the most used calculator'} on the home page.",
                               f"{top_row(cid)['value']} of {pl(n_, qd['one'])}." if top_row(cid) else "", "med", "site")]
        else:
            rules[cid] = []
        if qd.get("kind") == "whatsapp" and top_row(cid):
            rules[cid].append(step(f"Keep a WhatsApp button beside the content on {top_row(cid)['label']}.", f"{top_row(cid)['value']} of {pl(n_, 'click')} came from it.", "low", "site"))
        if qd.get("kind") in ("demo", "cta") and n_ and top_row(cid, len(qd["breakdowns"]) - 1):
            r0 = top_row(cid, len(qd["breakdowns"]) - 1)
            rules[cid].append(step(f"Repeat what works on {r0['label']} on similar pages.", f"{r0['value']} of {pl(n_, qd['one'])} came from it.", "low", "site"))
    if "sessions" in by:
        cty = {r["label"]: r["value"] for r in by["sessions"]["breakdowns"][1]["rows"]} if len(by["sessions"]["breakdowns"]) > 1 else {}
        mk, s_ = sum(cty.get(x, 0) for x in MARKET["countries"]), tot("sessions") or 1
        rules["sessions"] = [step("Exclude team traffic: add the team's IP addresses as internal traffic in Analytics.", f"{mk} of {s_} sessions came from {MARKET['the']}.", "high", "owner")]
        ch = top_row("sessions")
        if ch:
            rules["sessions"].append(step(f"Make sure the {ch['label']} landing pages carry the {CTA} button.", f"{ch['value']} of {s_} sessions.", "med", "site"))
    if "engaged" in by:
        e, s_ = tot("engaged") or 0, tot("sessions") or 1
        rules["engaged"] = [step("Tighten the first screen of entry pages: one line on who it is for, one figure, one button.", f"{round(100 * e / s_)}% of sessions engaged this week.", "med", "site")]
    if "newvisitors" in by:
        rules["newvisitors"] = [step(f"Watch {MARKET['label']} new visitors as the core number once team traffic is filtered.", "", "low", "owner")]
    if "views" in by and top_row("views"):
        rules["views"] = [step(f"Give {top_row('views')['label']} a direct path to the {CTA} form.", f"Most viewed page: {top_row('views')['value']} of {pl(tot('views'), 'view')}.", "med", "site")]
    if "impressions" in by:
        rules["impressions"] = []
        if unknown:
            rules["impressions"].append(step(f"Request indexing in Search Console for the {pl(unknown, 'page')} not in Google yet ({not_indexed_text(ix)}).",
                                             "", "high", "google"))
        rules["impressions"].append(step("Rewrite the title and description of the most shown pages to match the search wording.", "", "med", "site"))
    if "searchclicks" in by:
        rules["searchclicks"] = [step("Track clicks from searches without the brand name.", "", "low", "owner")]
    if "pageone" in by:
        near = by["pageone"]["breakdowns"][0]["rows"] if by["pageone"]["breakdowns"] else []
        rules["pageone"] = ([step(f"Strengthen the page for '{near[0]['label'].split(' (')[0]}': more depth, internal links, a clear answer at the top.", (lambda m: f"Position {m.group(1)}, {pl(near[0]['value'], 'impression')}." if m else "")(re.search(r"position (\d+)", near[0]['label'])), "high", "site")] if near else
                            [step("No keyword on page one yet: expected in the first weeks after launch.", "", "low", "google")])
    if "pages" in by:
        rules["pages"] = []
        ms = c.get("missing_from_sitemap") or []
        if ms:
            rules["pages"].append(step(f"Add the {pl(len(ms), 'linked page')} missing from the sitemap, or noindex {'it' if len(ms) == 1 else 'them'}: "
                                       + "; ".join(page_name(u) for u in ms[:3]) + ".", "", "med", "site"))
        ni = c.get("noindex") or []
        if ni:
            rules["pages"].append(step(f"Take the {pl(len(ni), 'noindex page')} out of the sitemap: " + "; ".join(page_name(u) for u in ni[:4]) + ".",
                                       "", "low", "site"))
        for code, lq in (q.get("lang") or {}).items():
            eo = lq.get("en_only") or []
            if eo:
                rules["pages"].append(step(f"Publish {LANG_NAME[code]} versions of the "
                                           + (pl(len(eo), f"{LANG_NAME[MAIN_LANG]}-only page") if len(OTHER_LANGS) == 1 else f"{pl(len(eo), 'page')} that have none") + ", starting with "
                                           + "; ".join(page_name(u) for u in eo[:3]) + ".", "", "med", "site"))
    if "broken" in by:
        rules["broken"] = ([step("Fix: " + "; ".join(u.replace(SITE, "") for u in c["broken"][:3]) + ".", "", "high", "site")] if c["broken"] else
                           [step("Nothing to fix. Recheck after each release.", "", "low", "site")])
    if "issues" in by:
        rules["issues"] = [step(f"Add share images to the {pl(len(c['issues'].get('No share image', [])), 'page')} without one.", "", "med", "site")] if c["issues"].get("No share image") else []
        if c["issues"].get("Description over 160 characters"):
            rules["issues"].append(step("Shorten the long descriptions: " + "; ".join(page_name(u) for u in c["issues"]["Description over 160 characters"][:3]) + ".", "", "low", "site"))
    if "speed" in by:
        sp = c.get("speed_pages", [])
        slow = [p for p in sp if p["ms"] >= 1000]
        heavy = max(sp, key=lambda p: p["kb"], default=None)
        rules["speed"] = []
        if c.get("slow_route"):
            slow = []
        elif c["ms_median"] and c["ms_median"] >= 500:
            rules["speed"].append(step("Bring the median under 500 ms: check server caching of the page code.", "", "high", "site"))
        if slow:
            rules["speed"].append(step("Check the slowest pages first: " + "; ".join(p["name"] for p in slow[:3]) + ".",
                                       f"{len(slow)} of {len(sp)} pages took over a second to answer.", "med", "site"))
        if heavy and heavy["types"] and heavy["kb"] >= 500:
            t0 = heavy["types"][0]
            rules["speed"].append(step(f"Reduce the {t0[0].lower()} on {heavy['name']} ({f(t0[1])} of {f(heavy['kb'])} KB).", "Heaviest page on the site.", "med", "site"))
        ts = c.get("top_shared")
        if ts and ts[3] >= len(sp) / 2 and ts[2] >= 50:
            rules["speed"].append(step(f"Trim {ts[0]} ({f(ts[2])} KB, loaded on {ts[3]} of {len(sp)} pages).",
                                       "", "med", "site"))
        elif c["weight"]:
            big = max(c["weight"].items(), key=lambda kv: kv[1])
            rules["speed"].append(step(f"Minify and split the home page {big[0].lower()} ({big[1]} KB).", "Largest part of the home page.", "low", "site"))
        if not rules["speed"]:
            rules["speed"] = [step("No action while the median stays under 500 ms.", "", "low", "site")]
    for k in ("refdomains", "authority"):
        if k in by:
            rules[k] = [step(t_, "", imp, own) for t_, imp, own in CFG.get("authority_steps", [
                ["Earn one link from a recognised UAE publication or industry body.", "high", "owner"],
                ["Get listed on Zoho, Xero and QuickBooks advisor directories.", "med", "owner"]])]
    for x in cards:
        if x["id"] in rules and "next" not in x:
            x["next"] = rules[x["id"]][:4]


# ---------------------------------------------------------------- main
def main():
    HIST.mkdir(parents=True, exist_ok=True)
    notes, cards = [], []
    ctl0 = control_ms()
    if ctl0 > CONTROL_LIMIT_MS:
        print(f"Skipped: this machine's network is slow (control {ctl0} ms); the last snapshot stays.", file=sys.stderr)
        return
    sess = google_session()
    google = {"ga": [], "sc": []}
    if sess:
        for name, fn in (("ga", ga_cards), ("sc", sc_cards)):
            try:
                google[name] = fn(sess)
            except Exception as e:
                notes.append(f"{'Google Analytics' if name == 'ga' else 'Search Console'} could not be read: {str(e)[:160]}")
                print(e, file=sys.stderr)
    else:
        notes.append("Google key not set: Analytics and Search Console cards are missing.")

    global CRAWL
    c = crawl()
    ctl1 = control_ms()
    if ctl1 > CONTROL_LIMIT_MS:
        print(f"Skipped: this machine's network turned slow during the crawl (control {ctl0} then {ctl1} ms); "
              "the last snapshot stays.", file=sys.stderr)
        return
    c["control_ms"] = [ctl0, ctl1]
    c["broken_n"] = len(c["broken"])
    # The score uses the median of this run and the two days before, so one slow moment on the host does not
    # swing it; the Page speed card still shows this run's reading (23 Nov 2026: A1 read 7,018 ms once, after 276).
    prev = []
    for f in sorted(HIST.glob("*.json")):
        if f.stem < iso(TODAY):
            try:
                v = json.loads(f.read_text()).get("crawl", {}).get("ms_median")
            except Exception:
                v = None
            if v:
                prev.append(v)
    pts = prev[-2:] + ([c["ms_median"]] if c.get("ms_median") else [])
    c["ms_steady"] = round(sorted(pts)[len(pts) // 2] if len(pts) % 2 else sum(sorted(pts)[len(pts) // 2 - 1:len(pts) // 2 + 1]) / 2) if pts else None
    # A reading many times slower than the usual one, while this machine's own network is quick, is the host's network
    # slowing the testing machine (24 Nov 2026), not the site: it shows on the card but is not scored.
    p7 = sorted(prev[-7:])
    ref = (p7[len(p7) // 2] if len(p7) % 2 else round((p7[len(p7) // 2 - 1] + p7[len(p7) // 2]) / 2)) if len(p7) >= 2 else None
    c["ms_ref"] = ref
    c["slow_route"] = bool(ref and c.get("ms_median") and c["ms_median"] > max(4 * ref, ref + 1500))
    if c["slow_route"]:
        c["ms_steady"] = ref
        notes.append(f"Pages answered in a median {c['ms_median']:,} ms from the testing machine, about {round(c['ms_median'] / ref)} times "
                     f"slower than usual, while its own network was quick; the host's network can slow such machines down. "
                     f"Page speed is scored on Google PageSpeed or the usual {ref:,} ms.")
    try:
        ps = psi_readings(sess)
    except Exception as e:
        ps = {"error": str(e)[:200]}
    fresh = ps.get("pages") and ps.get("at") and dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(ps["at"]) < dt.timedelta(days=3)
    c["psi"] = ps if fresh else {"error": ps.get("error")}
    CRAWL = c
    import cube as cube_mod
    cube = json.loads((DATA / "cube.json").read_text())
    AW = cube_mod.AW = cube.get("audit_label", "Audit").lower()
    g = {"sc_ok": bool(google["sc"]), "bing": cube.get("bing_verified", False)}
    if sess and google["sc"]:
        try:
            g["targets"] = target_presence(sess)
        except Exception as e:
            notes.append(f"Target searches could not be read: {str(e)[:120]}")
        try:
            g["index"] = index_status(sess, [u for u in c["urls"] if u not in set(c.get("noindex", []))])
        except Exception as e:
            print(e, file=sys.stderr)
            msg = str(e)
            notes.append(f"Indexation keeps its {AW} score: Search Console URL Inspection is not permitted for the service account (needs Full permission)."
                         if " 401" in msg or " 403" in msg else f"Indexation keeps its {AW} score: URL Inspection could not be read this run ({msg[:80]}).")
    if sess and google["ga"]:
        for k, fn in (("ai", ai_sessions), ("events", events_check)):
            try:
                g[k] = fn(sess)
            except Exception as e:
                print(f"{k}: {e}", file=sys.stderr)
    if sess:
        try:
            g["first_seen"] = first_seen(sess)
        except Exception as e:
            print(f"first_seen: {e}", file=sys.stderr)
    if c.get("links_unchecked"):
        notes.append(f"{c['links_unchecked']} linked pages outside the sitemap are not checked yet; the next runs check them.")
    if "error" in (c.get("q") or {}):
        notes.append(f"Page checks failed, so the page-based cube sub-metrics keep their {AW} scores: {c['q']['error'][:120]}")
    sm = json.loads((DATA / "semrush.json").read_text()) if (DATA / "semrush.json").exists() else None
    measured = cube_mod.measure(c, g, sm)
    if cube_mod.fill_baseline(cube, measured, TODAY):      # a new site: the first run's readings become its baseline
        (DATA / "cube.json").write_text(json.dumps(cube, ensure_ascii=False, indent=1))
    cs = cube_mod.score(cube, measured, TODAY)
    today = {"date": iso(TODAY), "crawl": {k: c[k] for k in ("pages_ok", "broken_n", "issue_pages", "ms_median", "weight_total")},
             "cube": {"overall": cs["overall"], "blocks": {b["id"]: b["score"] for b in cs["blocks"]}}}
    for card_ in google["ga"] + google["sc"]:
        today[card_["id"]] = card_["stats"]["total"]
    (HIST / f"{iso(TODAY)}.json").write_text(json.dumps(today, indent=1))
    hist = history()

    now_t = dt.datetime.now(dt.timezone.utc)
    runs = json.loads(RUNS.read_text()) if RUNS.exists() else []
    runs.append({"t": zkey(now_t), **{k: c[k] for k in CRAWL_KEYS}})
    runs = [r for r in runs if wparse(r["t"]) > now_t - dt.timedelta(days=40)]
    RUNS.write_text(json.dumps(runs))

    cards = [cube_card(cs, cube, history(days=70), g)] + google["ga"] + google["sc"] + crawl_cards(c, hist) + semrush_cards()
    try:
        crawl_windows(cards, history(days=400), runs)
        cube_windows(cards[0])
    except Exception as e:
        print("Windows:", e, file=sys.stderr)
    for x in cards:
        x.setdefault("wins", ["7d"])
        if x["source"] == SM:
            x["wins"], x["fixed"] = [], "Semrush is read by hand once a month, so this card shows month by month in every window."
    next_steps(cards, c, g)
    c.pop("robots", None)
    c.pop("urls", None)
    c.pop("speed_pages", None)
    meta = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
            "date": iso(TODAY), "notes": notes, "crawl": c, "index": g.get("index"), "launch": iso(LAUNCH), "first_seen": g.get("first_seen"), "control_ms": c.get("control_ms"),
            "ga_checks": {k: g[k] for k in ("ai", "events") if k in g}}
    out = {"meta": meta, "cards": cards}
    # Self-check (19 Nov 2026): every card and window must add up; a problem is shown on the board as a note.
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import check_board
        probs = check_board.check(json.loads(json.dumps(out)))
        if probs:
            notes.append(f"Self-check found {pl(len(probs), 'problem')}: " + "; ".join(probs[:3]) + ".")
            print("\n".join(probs), file=sys.stderr)
    except Exception as e:
        print("Self-check:", e, file=sys.stderr)
    (DATA / "cards.json").write_text(json.dumps(out, ensure_ascii=False))
    print(f"{len(cards)} cards; notes: {notes}")


if __name__ == "__main__":
    main()
