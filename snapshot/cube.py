"""Search visibility cube: scores the ten blocks each day.

Sub-metrics with an `auto` key in data/cube.json are measured from the day's
crawl and Google data; the rest keep their audit score (Nov 13) until updated
by hand. Stage targets are counted from the launch date.
"""
import datetime as dt
import json
import re
from pathlib import Path

AI_BOTS = ["GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "CCBot"]
clamp = lambda v: max(0.0, min(10.0, round(v, 1)))


def bot_allowed(robots, bot):
    groups, agents, rules, in_rules = [], [], [], False
    for line in robots.splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        k, v = [x.strip() for x in line.split(":", 1)]
        if k.lower() == "user-agent":
            if in_rules:
                groups.append((agents, rules))
                agents, rules, in_rules = [], [], False
            agents.append(v.lower())
        elif k.lower() in ("allow", "disallow"):
            in_rules = True
            rules.append((k.lower(), v))
    if agents:
        groups.append((agents, rules))
    mine = [r for a, r in groups if bot.lower() in a] or [r for a, r in groups if "*" in a]
    return not any(k == "disallow" and v == "/" for r in mine for k, v in r)


def measure(c, g):
    """Returns {auto_key: (score, evidence)} for whatever can be measured today."""
    n = c["n_ok"] or 1
    pas = c["pass"]
    share = lambda k: pas[k] / n
    out = {}
    sm_total = c["pages"] + len(c["missing_from_sitemap"])
    comp = c["pages"] / sm_total if sm_total else 0
    out["sitemap"] = (clamp(10 * (0.6 * comp + 0.4 * c["lastmod_share"])),
                      f"{c['pages']} pages listed; {len(c['missing_from_sitemap'])} live pages linked but not listed; "
                      f"{round(100 * c['lastmod_share'])}% carry a lastmod date.")
    out["status"] = (clamp(10 * c["pages_ok"] / max(1, c["pages"]) - 0.5 * len(c["broken"])),
                     f"{c['pages_ok']} of {c['pages']} pages load; {len(c['broken'])} broken links.")
    out["canon"] = (clamp(10 * share("canon")), f"{pas['canon']} of {n} pages have a matching canonical.")
    if c["ms_median"]:
        out["speed"] = (clamp(10 - (c["ms_median"] - 300) / 150), f"Median page fetch {c['ms_median']} ms from a US server.")
    out["mobile"] = (clamp(10 * c["viewport_share"] if c["https_redirect"] else 5 * c["viewport_share"]),
                     f"{round(100 * c['viewport_share'])}% of pages set a mobile viewport; HTTP {'redirects' if c['https_redirect'] else 'does not redirect'} to HTTPS.")
    out["titles"] = (clamp(10 * share("titles")), f"{pas['titles']} of {n} titles are present, unique and 25 to 65 characters.")
    out["meta"] = (clamp(10 * share("meta")), f"{pas['meta']} of {n} descriptions are present, unique and 70 to 160 characters.")
    out["h1"] = (clamp(10 * share("h1")), f"{pas['h1']} of {n} pages have exactly one H1.")
    out["links"] = (clamp(10 * c["inlinks_ge3"] / n), f"{c['inlinks_ge3']} of {n} pages have three or more internal links pointing to them.")
    out["alt"] = (clamp(10 * share("alt")), f"{pas['alt']} of {n} pages have alt text on every image and a share image.")
    out["schema"] = (clamp(10 * share("schema")), f"{pas['schema']} of {n} pages carry structured data; {c['ld_bad']} blocks fail to parse.")
    sa = c["sameas_home"]
    out["sameas"] = (9.0 if sa >= 4 else 7.0 if sa >= 2 else 5.0 if sa == 1 else 2.0, f"Home page lists {sa} sameAs profile links.")
    age = c["lastmod_age_median"]
    if age is not None:
        out["fresh"] = (10.0 if age <= 30 else 8.0 if age <= 90 else 6.0 if age <= 180 else 4.0,
                        f"Median page last updated {age} days ago (sitemap lastmod).")
    allowed = [b for b in AI_BOTS if bot_allowed(c["robots"], b)]
    out["aibots"] = (clamp(10 * len(allowed) / len(AI_BOTS)), f"robots.txt allows {len(allowed)} of {len(AI_BOTS)} AI crawlers ({', '.join(allowed) or 'none'}).")
    out["llms"] = (9.0 if c["llms_txt"] else 1.0, "llms.txt is published." if c["llms_txt"] else "No llms.txt at the site root.")
    if c["hreflang_pages"]:
        out["hreflang"] = (clamp(10 * c["hreflang_ok"] / c["hreflang_pages"]),
                           f"{c['hreflang_ok']} of {c['hreflang_pages']} pages have hreflang pairs that point back.")
    if g.get("targets") is not None:
        t = g["targets"]
        out["presence"] = (clamp(10 * t["shown"] / t["total"]), f"{t['shown']} of {t['total']} target searches showed the site in Google in the last 28 days.")
        out["arquery"] = (clamp(10 * t["ar_shown"] / t["ar_total"]) if t["ar_total"] else 0.0,
                          f"{t['ar_shown']} of {t['ar_total']} Arabic target searches showed the site.")
    if g.get("index") is not None:
        ix = g["index"]
        out["index"] = (clamp(10 * ix["indexed"] / max(1, ix["checked"])), f"{ix['indexed']} of {ix['checked']} pages are indexed by Google (URL Inspection).")
    if g.get("sc_ok"):
        out["sc"] = (10.0 if g.get("bing") else 6.0,
                     "Search Console verified and feeding daily" + ("; Bing verified." if g.get("bing") else "; Bing Webmaster Tools not verified yet."))
    return out


def stage_of(cube, day):
    for i, s in enumerate(cube["stages"]):
        if s["until"] is None or day <= dt.date.fromisoformat(s["until"]):
            return i, s
    return len(cube["stages"]) - 1, cube["stages"][-1]


def score(cube, measured, day):
    si, stage = stage_of(cube, day)
    blocks, overall = [], 0.0
    for b in cube["blocks"]:
        subs = []
        for s in b["subs"]:
            m = measured.get(s["auto"]) if s["auto"] else None
            subs.append({**s, "score": m[0] if m else s["audit"], "source": "Measured daily" if m else "Audit, Nov 13",
                         "evidence_now": m[1] if m else s.get("evidence", "")})
        val = round(sum(x["weight"] * x["score"] for x in subs) / sum(x["weight"] for x in subs), 2)
        target = cube["target_groups"][b["group"]][si]
        overall += b["weight"] * val / 100
        blocks.append({"id": b["id"], "name": b["name"], "weight": b["weight"], "score": val, "target": target,
                       "audit": round(sum(x["weight"] * x["audit"] for x in b["subs"]) / sum(x["weight"] for x in b["subs"]), 2),
                       "cards": b["cards"], "subs": subs})
    target_overall = round(sum(b["weight"] * b["target"] for b in blocks) / 100, 2)
    return {"overall": round(overall, 2), "target": target_overall, "stage": stage["name"], "stage_index": si,
            "stage_until": stage["until"], "blocks": blocks}
