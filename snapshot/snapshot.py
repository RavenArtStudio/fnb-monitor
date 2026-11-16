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
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HIST = DATA / "history"
SITE = "https://fnbperformance.com"
GA_PROPERTY = "557948137"          # F&B Performance UAE - GA4 (stream G-ZESHDWC1FD)
SC_SITE = "sc-domain:fnbperformance.com"
HOSTS = ["fnbperformance.com", "www.fnbperformance.com"]
K = "fnb-performance"
UA = "fnb-monitor/1.0 (+https://github.com/RavenArtStudio/fnb-monitor)"

TODAY = dt.datetime.now(dt.timezone(dt.timedelta(hours=4))).date()   # Dubai
GA = "Google Analytics"
SC = "Google Search Console"
CR = "Site crawl"
SM = "Semrush"
CONSENT = ("Google Analytics loads only after a visitor accepts cookies, so visitors "
           "who decline or ignore the banner are not counted.")
EVENT_NOTE = "seen in the site code, Nov 16"

f = lambda n: f"{n:,}" if isinstance(n, int) else (f"{n:,.1f}" if isinstance(n, float) else str(n))
iso = lambda d: d.isoformat()
short = lambda d: f"{d.strftime('%b')} {d.day}"


def page_name(path):
    """'/ae/ar/tools/vat-calculator' -> 'Vat calculator, Arabic'."""
    p = re.sub(r"^/ae(?=/|$)", "", (path or "/").split("?")[0].rstrip("/"))
    ar = bool(re.match(r"^/ar(/|$)", p))
    p = re.sub(r"^/ar(?=/|$)", "", p)
    if p in ("", "/"):
        name = "Home"
    else:
        name = p.strip("/").split("/")[-1].replace("-", " ")
        name = name[:1].upper() + name[1:]
    return name + (", Arabic" if ar else "")


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
                "https://www.googleapis.com/auth/webmasters.readonly"])
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


def sc(sess, start, end, dims, limit=1000):
    url = ("https://searchconsole.googleapis.com/webmasters/v3/sites/"
           + requests.utils.quote(SC_SITE, safe="") + "/searchAnalytics/query")
    r = sess.post(url, json={"startDate": iso(start), "endDate": iso(end),
                             "dimensions": dims, "rowLimit": limit, "dataState": "final"}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"SC {r.status_code}: {r.text[:300]}")
    return r.json().get("rows", [])


# ---------------------------------------------------------------- card builders
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
            "health": [{"site": "FNB Performance", "statusLabel": "Live", "through": days[-1], "via": source}],
            "main": {"dates": days, "series": {K: [{"date": d, "value": v} for d, v in zip(days, cur)]},
                     "previous": [{"date": d, "value": v} for d, v in zip(days, prev)],
                     "tipLabel": "A week earlier" if level else f"Previous {len(cur)} days"},
            "breakdowns": [{"id": f"b{n}", "title": b[0], "rows": [{"label": r[0], "value": r[1]} for r in b[1]]} for n, b in enumerate(breakdowns)],
            "patterns": pats, "questions": q,
            "raw": {"columns": ["Date", "Site", label, "Previous period"],
                    "rows": [[d, "FNB Performance", v, p] for d, v, p in zip(days, cur, prev)]},
            "howCalculated": how}


def reading(id, label, short_label, unit, group, source, fields, dates, vals, sub, breakdowns, nxt, how,
            caveats, heading="Day by day", pats=None, lower_better=False):
    """Card for a level reading over stored history (crawl, Semrush). None = no reading that day."""
    have = [(d, v) for d, v in zip(dates, vals) if v is not None]
    tot = have[-1][1]
    prior = have[-2] if len(have) > 1 else None
    if prior is None:
        delta, rail, tone = f"First reading, {short(dt.date.fromisoformat(have[-1][0]))}", "new", ""
    else:
        x = tot - prior[1]
        when = short(dt.date.fromisoformat(prior[0]))
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
            "health": [{"site": "FNB Performance", "statusLabel": "Live", "through": have[-1][0], "via": source}],
            "main": {"dates": dates, "heading": heading, "series": {K: [{"date": d, "value": v} for d, v in zip(dates, vals)]}},
            "breakdowns": [{"id": f"b{n}", "title": b[0], "rows": [{"label": r[0], "value": r[1]} for r in b[1]]} for n, b in enumerate(breakdowns)],
            "patterns": pats or [], "questions": q,
            "raw": {"columns": ["Date", "Site", label], "rows": [[d, "FNB Performance", v] for d, v in zip(dates, vals)]},
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

    # Enquiries: the site's own funnel events
    ev = ga(sess, start, end, ["date", "eventName"], ["eventCount"],
            {"filter": {"fieldName": "eventName", "inListFilter": {"values": ["generate_lead", "whatsapp_click", "tool_used"]}}})
    def ev_series(name, days):
        return series([(d, m) for d, m in ev if d[1] == name], days)
    def ev_break(name, dims):
        try:
            return ga(sess, w0, end, dims, ["eventCount"],
                      {"filter": {"fieldName": "eventName", "stringFilter": {"value": name}}}, order="eventCount")
        except RuntimeError as e:
            print(e, file=sys.stderr)
            return []

    leads_c, leads_p = ev_series("generate_lead", cur_days), ev_series("generate_lead", prev_days)
    cards.append(card("leads", "Profit Review requests", "requests", "Enquiries", GA,
        "eventName = generate_lead, eventCount, pagePath, sessionDefaultChannelGroup", cur_days, leads_c, leads_p,
        [("Page the request was sent from", top(ev_break("generate_lead", ["pagePath"]), label=lambda d: page_name(d[0])), "Which page were requests sent from?", "Page"),
         ("Channel that brought them", top(ev_break("generate_lead", ["sessionDefaultChannelGroup"])), "Which channel brought them?", "Channel")],
        (f"{sum(leads_c)} requests this week", "Match each request to its reply so none goes unanswered."),
        "Count of the generate_lead event the site sends when the Profit Review form is sent successfully.",
        fx([f"The site sends generate_lead when the form is sent ({EVENT_NOTE}).", "Requests made by phone, email or WhatsApp are not counted here."]),
        short_label="Profit Review requests"))

    wa_c, wa_p = ev_series("whatsapp_click", cur_days), ev_series("whatsapp_click", prev_days)
    cards.append(card("whatsapp", "WhatsApp clicks", "clicks", "Enquiries", GA,
        "eventName = whatsapp_click, eventCount, pagePath", cur_days, wa_c, wa_p,
        [("Page the click came from", top(ev_break("whatsapp_click", ["pagePath"]), label=lambda d: page_name(d[0])), "Which pages produce WhatsApp clicks?", "Page")],
        None, "Count of the whatsapp_click event the site sends.",
        fx([f"The site sends whatsapp_click from its Ask buttons ({EVENT_NOTE}); header and footer links are not yet confirmed.",
            "A click opens WhatsApp; it does not prove a message was sent."])))

    tool_rows = ev_break("tool_used", ["customEvent:tool"])
    tool_dim = "customEvent:tool"
    if not tool_rows or all(d[0] in ("(not set)", "") for d, _ in tool_rows):
        tool_rows, tool_dim = ev_break("tool_used", ["pagePath"]), "pagePath"
    tu_c, tu_p = ev_series("tool_used", cur_days), ev_series("tool_used", prev_days)
    cards.append(card("tools", "Calculator uses", "uses", "Enquiries", GA,
        f"eventName = tool_used, eventCount, {tool_dim}", cur_days, tu_c, tu_p,
        [("By calculator", top(tool_rows, 8, label=lambda d: (d[0].replace('-', ' ').capitalize() if tool_dim != 'pagePath' else page_name(d[0]))), "Which calculators are used most?", "Calculator")],
        None, "Count of the tool_used event the site sends when a calculator is used.",
        fx([f"The site sends tool_used with the calculator name ({EVENT_NOTE})."]
           + (["The tool parameter is not registered as a custom dimension, so calculators are split by page instead."] if tool_dim == "pagePath" else []))))

    # Website
    daily = ga(sess, start, end, ["date"], ["sessions", "engagedSessions", "newUsers", "screenPageViews"])
    col = lambda i, days: series(daily, days, val=lambda m: m[i])
    ch = ga(sess, w0, end, ["sessionDefaultChannelGroup"], ["sessions"], order="sessions")
    cty = ga(sess, w0, end, ["country"], ["sessions"], order="sessions")
    lp = ga(sess, w0, end, ["landingPage"], ["sessions"], order="sessions", limit=50)
    dev = ga(sess, w0, end, ["deviceCategory"], ["sessions"], order="sessions")
    s_c, s_p = col(0, cur_days), col(0, prev_days)
    uae = sum(int(m[0]) for d, m in cty if d[0] == "United Arab Emirates")
    cards.append(card("sessions", "Website sessions", "sessions", "Website", GA,
        "date, sessions, sessionDefaultChannelGroup, country, landingPage, deviceCategory", cur_days, s_c, s_p,
        [("Where visitors come from", top(ch), "Where do visitors come from?", "Channel"),
         ("Country", top(cty), "Which countries are they in?", "Country"),
         ("Entry page", top(lp, label=lambda d: page_name(d[0])), "Which pages do visits start on?", "Entry page"),
         ("Device", top(dev), "What are they browsing on?", "Device")],
        (f"{uae} of {sum(s_c)} sessions from the UAE", "The UAE share is the one that matters; the rest is partly the team."),
        "Sessions on the live site hostnames. The previous period is the 7 days immediately before.",
        fx(["Visits from development hosts are excluded.", "Visits by the team count until internal traffic is filtered in Google Analytics."])))

    eng = ga(sess, w0, end, ["landingPage"], ["engagedSessions"], order="engagedSessions", limit=50)
    e_c, e_p = col(1, cur_days), col(1, prev_days)
    cards.append(card("engaged", "Engaged sessions", "sessions", "Website", GA,
        "date, engagedSessions, landingPage", cur_days, e_c, e_p,
        [("Entry page of engaged sessions", top(eng, label=lambda d: page_name(d[0])), "Which entry pages hold attention?", "Entry page")],
        (f"{sum(e_c)} of {sum(s_c)} sessions stayed to read", "Compare the entry pages that hold visitors with the ones that lose them."),
        "Sessions that lasted over 10 seconds, viewed two or more pages, or fired a key event.", fx([])))

    nvr = ga(sess, w0, end, ["newVsReturning"], ["activeUsers"], order="activeUsers")
    ncty = ga(sess, w0, end, ["country"], ["newUsers"], order="newUsers")
    n_c, n_p = col(2, cur_days), col(2, prev_days)
    cards.append(card("newvisitors", "New visitors", "visitors", "Website", GA,
        "date, newUsers, newVsReturning, country", cur_days, n_c, n_p,
        [("New against returning", top(nvr, label=lambda d: d[0].capitalize() if d[0] else "Unknown"), "How many are new?", "Visitor"),
         ("Country of new visitors", top(ncty), "Where are new visitors from?", "Country")],
        None, "People with no earlier visit to the site.",
        fx(["Team members count as new on each new device until internal traffic is filtered."])))

    pv = ga(sess, w0, end, ["pagePath"], ["screenPageViews"], order="screenPageViews", limit=50)
    v_c, v_p = col(3, cur_days), col(3, prev_days)
    cards.append(card("views", "Page views", "views", "Website", GA,
        "date, screenPageViews, pagePath", cur_days, v_c, v_p,
        [("By page", top(pv, 8, label=lambda d: page_name(d[0])), "Which pages are viewed most?", "Page")],
        None, "Every page load on the live site, repeats included.", fx([])))
    return cards


# ---------------------------------------------------------------- Search Console cards
def sc_cards(sess):
    rows = sc(sess, TODAY - dt.timedelta(days=30), TODAY - dt.timedelta(days=1), ["date"])
    if not rows:
        return []
    last = max(dt.date.fromisoformat(r["keys"][0]) for r in rows)
    cur_days, prev_days = window(last)
    by = {dt.date.fromisoformat(r["keys"][0]): r for r in rows}
    get = lambda days, k: [int(by[d][k]) if d in by else 0 for d in days]
    w = (cur_days[0], last)
    q = sc(sess, *w, ["query"], 200)
    pg = sc(sess, *w, ["page"], 100)
    qtop = lambda k: [(r["keys"][0], int(r[k])) for r in sorted(q, key=lambda r: -r[k]) if r[k] > 0][:6]
    ptop = lambda k: [(page_name(urlparse(r["keys"][0]).path), int(r[k])) for r in sorted(pg, key=lambda r: -r[k]) if r[k] > 0][:6]
    lag = ["Google reports search data two to three days late, so the window ends on the latest complete day.",
           "Rare queries are withheld by Google for privacy, so query rows add up to less than the total."]
    sub = f"{SC}, {short(cur_days[0])} to {short(last)}"
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
    return cards


# ---------------------------------------------------------------- Site crawl
class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title, self.in_title, self.desc, self.h1, self.canon, self.noindex = "", False, "", 0, "", False
        self.og, self.imgs, self.noalt, self.links, self.schema, self.lang = False, 0, 0, [], 0, ""
        self.res = []

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
        elif tag == "h1":
            self.h1 += 1
        elif tag == "link":
            rel = (a.get("rel") or "").lower()
            if rel == "canonical":
                self.canon = a.get("href", "")
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
            if a.get("src"):
                self.res.append(a["src"])

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, d):
        if self.in_title:
            self.title += d


def fetch(url):
    t = time.perf_counter()
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30, allow_redirects=True)
        return r, round((time.perf_counter() - t) * 1000)
    except requests.RequestException:
        return None, round((time.perf_counter() - t) * 1000)


def crawl():
    sm, _ = fetch(SITE + "/sitemap.xml")
    urls = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sm.text if sm else "")
    pages = {}

    def one(u):
        r, ms = fetch(u)
        o = {"u": urlparse(u).path or "/", "status": r.status_code if r is not None else 0, "ms": ms,
             "redir": bool(r is not None and r.history)}
        if r is not None and r.status_code == 200:
            p = Page()
            p.feed(r.text)
            o.update(title=p.title.strip(), desc=p.desc, h1=p.h1, canon=urlparse(p.canon).path if p.canon else "",
                     noindex=p.noindex, og=p.og, imgs=p.imgs, noalt=p.noalt, schema=p.schema, lang=p.lang,
                     links=sorted({urljoin(u, h).split("#")[0] for h in p.links if urljoin(u, h).startswith(SITE)}),
                     res=[urljoin(u, x) for x in p.res], kb=round(len(r.content) / 1024))
        return o

    with cf.ThreadPoolExecutor(6) as ex:
        for o in ex.map(one, urls):
            pages[o["u"]] = o
    known = {u.rstrip("/") for u in urls}
    extra = sorted({l for o in pages.values() for l in o.get("links", []) if l.rstrip("/") not in known})

    def chk(u):
        r, _ = fetch(u)
        return u, (r.status_code if r is not None else 0)
    with cf.ThreadPoolExecutor(6) as ex:
        linkres = dict(ex.map(chk, extra))
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
    # Home page size: the page plus every file it references directly
    home = pages.get("/ae") or next(iter(ok), None)
    weight = {"Page": home["kb"] if home else 0, "Fonts": 0, "Styles": 0, "Scripts": 0, "Images": 0}
    nfiles = 1
    if home:
        for u in sorted(set(home["res"])):
            if not u.startswith(SITE):
                continue
            r, _ = fetch(u)
            if r is None or r.status_code != 200:
                continue
            nfiles += 1
            ext = urlparse(u).path.rsplit(".", 1)[-1].lower()
            kind = "Fonts" if ext in ("woff2", "woff", "ttf") else "Styles" if ext == "css" else "Scripts" if ext == "js" else "Images"
            weight[kind] += len(r.content) / 1024
    weight = {k: round(v) for k, v in weight.items()}
    ms = sorted(o["ms"] for o in ok)
    slow = sorted(ok, key=lambda o: -o["ms"])[:5]
    return {
        "date": iso(TODAY),
        "pages": len(pages), "pages_ok": len(ok),
        "lang": {"English": sum(1 for o in ok if o["lang"].startswith("en")), "Arabic": sum(1 for o in ok if o["lang"].startswith("ar"))},
        "redirects": sum(1 for o in pages.values() if o["redir"]), "errors": len(pages) - len(ok),
        "extra_links": len(extra), "broken": [u for u, s in linkres.items() if s != 200] + [o["u"] for o in pages.values() if o["status"] != 200],
        "issues": {k: v for k, v in issues.items()}, "issue_pages": len({u for v in issues.values() for u in v}),
        "ms_median": ms[len(ms) // 2] if ms else None, "ms_max": ms[-1] if ms else None,
        "slowest": [[page_name(o["u"]), o["ms"]] for o in slow],
        "weight": weight, "weight_total": sum(weight.values()), "files": nfiles,
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
    sub = f"{CR}, read {short(TODAY)}, live figures"
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
                       "evidence": f"{c['lang']['English']} English, {c['lang']['Arabic']} Arabic; {c['errors']} errors."}]),
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
        reading("response", "Server response time", "Response time, ms", "ms", "Site health", CR, "time to fetch each page, in milliseconds",
                dates, v("ms_median"), sub,
                [("Slowest pages, ms", c["slowest"], "Which pages are slowest?", "Page", "ms")],
                None, "Median time to download the page code across the sitemap pages, in milliseconds.",
                ["Measured from a GitHub server in the United States; visitors in the UAE will see different times.",
                 "This is the page code only, not the time to draw the page."] + once, lower_better=True),
        reading("weight", "Home page size", "Home page size, KB", "KB", "Site health", CR, "size of the home page and each file it references",
                dates, v("weight_total"), sub,
                [("By file type, KB", sorted(c["weight"].items(), key=lambda x: -x[1]), "What makes up the size?", "Type", "KB")],
                None, f"Uncompressed size of the home page and the {c['files'] - 1} files it references directly.",
                ["Uncompressed sizes; the transfer over the network is smaller.",
                 "Google Analytics, which loads after cookies are accepted, is not included."] + once, lower_better=True),
    ]
    return cards


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
                s.get("next_domains"), f"Websites with at least one link to fnbperformance.com, counted by Semrush each month. {s['backlinks']} backlinks in total.",
                ["Refreshed by hand during working sessions, not daily.", "Semrush finds links by its own crawl, so new links appear with a delay."],
                heading="Month by month", pats=s.get("patterns_domains")),
        reading("authority", "Authority score", "Authority score, of 100", "points", "Authority", SM,
                "backlinks_overview: authority_score", dates, [r["score"] for r in m], sub,
                [("What Semrush sees", [("Referring domains", m[-1]["domains"]), ("Backlinks", s["backlinks"]), ("Keywords ranking in the UAE", s["uae_keywords"])], "What is the score built on?", "Measure", "Count")],
                s.get("next_score"), "Semrush Authority Score for the domain, 0 to 100, from link quality, search traffic and spam signals.",
                ["A third-party estimate, not a Google number.", "Refreshed by hand during working sessions, not daily."],
                heading="Month by month", pats=s.get("patterns_score")),
    ]


# ---------------------------------------------------------------- main
def main():
    HIST.mkdir(parents=True, exist_ok=True)
    notes, cards = [], []
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

    c = crawl()
    c["broken_n"] = len(c["broken"])
    today = {"date": iso(TODAY), "crawl": {k: c[k] for k in ("pages_ok", "broken_n", "issue_pages", "ms_median", "weight_total")}}
    for card_ in google["ga"] + google["sc"]:
        today[card_["id"]] = card_["stats"]["total"]
    (HIST / f"{iso(TODAY)}.json").write_text(json.dumps(today, indent=1))
    hist = history()

    cards = google["ga"] + google["sc"] + crawl_cards(c, hist) + semrush_cards()
    meta = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
            "date": iso(TODAY), "notes": notes, "crawl": c}
    (DATA / "cards.json").write_text(json.dumps({"meta": meta, "cards": cards}, ensure_ascii=False))
    print(f"{len(cards)} cards; notes: {notes}")


if __name__ == "__main__":
    main()
