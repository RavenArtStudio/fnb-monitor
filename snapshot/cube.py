"""Search visibility cube: scores the ten blocks each day.

Sub-metrics with an `auto` key in data/cube.json are measured from the day's
crawl and Google data; the rest keep their audit score (Nov 13) until updated
by hand. Stage targets are counted from the launch date.
"""
import datetime as dt
from siteconf import CFG, LANG_NAME, MAIN_LANG, OTHER_LANGS

AW = "audit"     # "baseline" for sites whose starting scores are their first readings; set by snapshot.py
import re

AI_BOTS = ["GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "CCBot"]
clamp = lambda v: max(0.0, min(10.0, round(v, 1)))
pl = lambda k, w, s="s": f"{k} {w}{'' if k == 1 else s}"


def robot_groups(robots):
    groups, agents, rules, in_rules = [], [], [], False
    for line in (robots or "").splitlines():
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
    return groups


def rules_for(robots, bot):
    groups = robot_groups(robots)
    return [r for a, r in groups if bot.lower() in a] or [r for a, r in groups if "*" in a]


def bot_allowed(robots, bot):
    return not any(k == "disallow" and v == "/" for r in rules_for(robots, bot) for k, v in r)


def path_allowed(robots, bot, path):
    """Google's rule: the longest matching Allow or Disallow wins; Allow wins a tie. Supports * and $."""
    best = (-1, True)
    for r in rules_for(robots, bot):
        for k, v in r:
            if not v:
                continue
            rx = "^" + re.escape(v).replace(r"\*", ".*").replace(r"\$", "$")
            if re.match(rx, path):
                cand = (len(v), k == "allow")
                if cand[0] > best[0] or (cand[0] == best[0] and cand[1]):
                    best = cand
    return best[1]


def measure(c, g, sm=None):
    """Returns {auto_key: (score, evidence[, part[, source]])} for whatever can be measured today.

    part is the share of the sub-metric the rule covers (default 1); the rest keeps the audit score.
    """
    n = c["n_ok"] or 1
    pas = c["pass"]
    share = lambda k: pas[k] / n
    out = {}
    sm_total = c["pages"] + len(c["missing_from_sitemap"])
    comp = c["pages"] / sm_total if sm_total else 0
    out["sitemap"] = (clamp(10 * (0.6 * comp + 0.4 * c["lastmod_share"])),
                      f"{c['pages']} pages listed; {pl(len(c['missing_from_sitemap']), 'live page')} linked but not listed; "
                      f"{round(100 * c['lastmod_share'])}% carry a lastmod date.")
    out["status"] = (clamp(10 * c["pages_ok"] / max(1, c["pages"]) - 0.5 * len(c["broken"])),
                     f"{c['pages_ok']} of {c['pages']} pages load; {pl(len(c['broken']), 'broken link')}.")
    out["canon"] = (clamp(10 * share("canon")), f"{pas['canon']} of {n} pages have a matching canonical.")
    if c["ms_median"]:
        st = c.get("ms_steady") or c["ms_median"]
        out["speed"] = (clamp(10 - (st - 300) / 150),
                        f"Median page fetch {c['ms_median']} ms from a US server." if st == c["ms_median"] else
                        f"Median page fetch {st} ms over this run and the two days before, from a US server; {c['ms_median']} ms in this run.")
    out["mobile"] = (clamp(10 * c["viewport_share"] if c["https_redirect"] else 5 * c["viewport_share"]),
                     f"{round(100 * c['viewport_share'])}% of pages set a mobile viewport; HTTP {'redirects' if c['https_redirect'] else 'does not redirect'} to HTTPS.")
    out["titles"] = (clamp(10 * share("titles")), f"{pas['titles']} of {n} titles are present, unique and 25 to 65 characters.")
    out["meta"] = (clamp(10 * share("meta")), f"{pas['meta']} of {n} descriptions are present, unique and 70 to 160 characters.")
    out["h1"] = (clamp(10 * share("h1")), f"{pas['h1']} of {n} pages have exactly one H1.")
    out["links"] = (clamp(10 * c["inlinks_ge3"] / n), f"{c['inlinks_ge3']} of {n} pages have three or more internal links pointing to them.")
    out["alt"] = (clamp(10 * share("alt")), f"{pas['alt']} of {n} pages have alt text on every image and a share image.")
    out["schema"] = (clamp(10 * share("schema")), f"{pas['schema']} of {n} pages carry structured data; {c['ld_bad']} blocks fail to parse or lack @context.")
    sa = c["sameas_home"]
    out["sameas"] = (9.0 if sa >= 4 else 7.0 if sa >= 2 else 5.0 if sa == 1 else 2.0, f"Home page lists {pl(sa, 'sameAs profile link')}.")
    age = c["lastmod_age_median"]
    if age is not None:
        out["fresh"] = (10.0 if age <= 30 else 8.0 if age <= 90 else 6.0 if age <= 180 else 4.0,
                        f"Median page last updated {pl(age, 'day')} ago (sitemap lastmod).")
    allowed = [b for b in AI_BOTS if bot_allowed(c["robots"], b)]
    out["aibots"] = (clamp(10 * len(allowed) / len(AI_BOTS)), f"robots.txt allows {len(allowed)} of {len(AI_BOTS)} AI crawlers ({', '.join(allowed) or 'none'}).")
    out["llms"] = (9.0 if c["llms_txt"] else 1.0, "llms.txt is published." if c["llms_txt"] else "No llms.txt at the site root.")
    if "indexnow_key_ok" in c:
        # Key file live and matching: 7 (IndexNow engines accept the site's pings). Sitemap named in robots.txt: 2.
        # The last point needs Bing Webmaster Tools, where IndexNow receipts can be confirmed.
        k, smap, bing = c["indexnow_key_ok"], c.get("robots_sitemap", False), bool(g.get("bing"))
        out["indexnow"] = (clamp(7.0 * k + 2.0 * smap + 1.0 * (k and bing)),
                           f"IndexNow key file {'is live and matches' if k else 'is missing or does not match'}; "
                           f"robots.txt {'names' if smap else 'does not name'} the sitemap; "
                           + ("Bing verified, so receipts can be confirmed." if bing else "receipts can be confirmed once Bing Webmaster Tools is verified."))
    if c["hreflang_pages"]:
        out["hreflang"] = (clamp(10 * c["hreflang_ok"] / c["hreflang_pages"]),
                           f"{c['hreflang_ok']} of {c['hreflang_pages']} pages have hreflang pairs that point back.")
    if g.get("targets") is not None and g["targets"]["total"]:
        t = g["targets"]
        out["presence"] = (clamp(10 * t["shown"] / t["total"]), f"{t['shown']} of {t['total']} target searches showed the site in Google in the last 28 days.")
    if g.get("targets") is not None and g["targets"].get("ar_total"):
        t = g["targets"]
        out["arquery"] = (clamp(10 * t["ar_shown"] / t["ar_total"]) if t["ar_total"] else 0.0,
                          f"{t['ar_shown']} of {t['ar_total']} Arabic target searches showed the site in Google in the last 28 days.")
    if g.get("index") is not None:
        ix = g["index"]
        ni = len(c.get("noindex", []))
        out["index"] = (clamp(10 * ix["indexed"] / max(1, ix["checked"])),
                        f"{ix['indexed']} of {ix['checked']} indexable pages are in Google (URL Inspection)"
                        + (f"; {pl(ni, 'page')} set to noindex on purpose are left out" if ni else "")
                        + (f"; {pl(ix['failed_now'], 'page')} kept the last reading after Search Console did not answer." if ix.get("failed_now") else "."))
    if g.get("sc_ok"):
        out["sc"] = (10.0 if g.get("bing") else 6.0,
                     "Search Console verified and feeding daily" + ("; Bing verified." if g.get("bing") else "; Bing Webmaster Tools not verified yet."))
    q = c.get("q") or {}
    if "error" in q or not q:
        return out
    for k, fn in RULES.items():
        try:
            r = fn(c, q, g, sm)
            if r:
                out[k] = r
        except Exception as e:   # one broken rule must not stop the rest; the sub keeps its audit score
            print(f"cube rule {k}: {e}")
    return out


def _list(xs, n=3):
    from quality import page_name
    xs = [page_name(x) for x in xs]
    return "; ".join(xs[:n]) + (f" and {len(xs) - n} more" if len(xs) > n else "")


def r_crawl(c, q, g, sm):
    ix = q["indexable"]
    n = ix["n"] or 1
    good = n - len(set(ix["noindex"]) | set(ix["blocked"]))
    v = 10 * (0.2 * c.get("robots_ok", False) + 0.2 * c.get("robots_sitemap", False) + 0.6 * good / n)
    ev = (f"robots.txt {'loads' if c.get('robots_ok') else 'is missing'} and {'names' if c.get('robots_sitemap') else 'does not name'} the sitemap; "
          f"{good} of {n} listed pages are open to Google")
    bits = []
    if ix["noindex"]:
        bits.append(f"{len(ix['noindex'])} set to noindex ({_list(ix['noindex'])})")
    if ix["blocked"]:
        bits.append(f"{len(ix['blocked'])} blocked by robots.txt")
    return clamp(v), ev + (", " + " and ".join(bits) if bits else "") + "."


def r_intent(c, q, g, sm):
    t = q["intent"]
    miss = [r[0] for r in sorted(t["rows"], key=lambda r: r[1]) if r[1] < 1]
    return (clamp(10 * t["pass"] / t["total"]) if t["total"] else 0.0,
            f"{t['pass']} of {t['total']} target searches have a page whose title and H1 carry every topic word of the search"
            + (f"; weakest: {', '.join(miss[:3])}." if miss else "."))


def r_cluster(c, q, g, sm):
    cl = q["clusters"]
    if not cl:
        return None
    thin = [x for x in cl if x["score"] < 1]
    desc = [f"{x['name']} (" + ", ".join(f"{x.get('counts', x).get(c_, 0)} {LANG_NAME[c_]}" for c_ in LANG_NAME) + ")" for x in thin[:3]]
    return (clamp(10 * sum(x["score"] for x in cl) / len(cl)),
            f"{len(cl) - len(thin)} of {len(cl)} topics have three or more pages" + (" in each language" if OTHER_LANGS else "")
            + (f"; thin: {'; '.join(desc)}." if thin else "."))


def r_depth(c, q, g, sm):
    d = q["depth"]
    L = d.get("langs") or {"en": {"n": d["en_n"], "med": d["en_med"]}, "ar": {"n": d["ar_n"], "med": d["ar_med"]}}
    if not L.get(MAIN_LANG, {}).get("n"):
        return None
    goal = lambda c_: 1200 if c_ == MAIN_LANG else 1000
    parts = [min(1, L[c_]["med"] / goal(c_)) if L.get(c_, {}).get("n") else 0 for c_ in LANG_NAME]
    bits = [f"{L[c_]['med']:,} in {LANG_NAME[c_]} ({L[c_]['n']})" for c_ in LANG_NAME if c_ in L]
    bits[0] = bits[0].replace(" in ", " words in ", 1)
    txt = bits[0] if len(bits) == 1 else ", ".join(bits[:-1]) + " and " + bits[-1]
    gl = [f"{goal(c_):,}" for c_ in LANG_NAME]
    goals = gl[0] if len(gl) == 1 else ", ".join(gl[:-1]) + " and " + gl[-1]
    what = "Guides and service pages" if CFG.get("depth_pages") == "content" else "Guides"
    return (clamp(10 * sum(parts) / len(parts)), f"{what} run a median {txt}, against {goals}; accuracy keeps the {AW} score.", 0.6)


def r_eeat(c, q, g, sm):
    e = q["eeat"]
    if not e["arts"]:
        return None
    by = (e["by_art"] + e["by_svc"]) / max(1, e["arts"] + e["svc"])
    about = 1.0 if len(e["creds"]) >= 2 else 0.5 if e["creds"] else 0.0
    v = 10 * (0.25 * by + 0.25 * e["dated"] / e["arts"] + 0.3 * e["cited"] / e["arts"] + 0.2 * about)
    return (clamp(v), f"Named author on {e['by_art']} of {e['arts']} guides and {e['by_svc']} of {e['svc']} service pages; "
            f"{e['dated']} guides dated; {e['cited']} cite an outside source; About page shows "
            + (", ".join(e["creds"][:4]) if e["creds"] else "no credentials") + ".")


def r_assets(c, q, g, sm):
    a = q["assets"]
    k = a["tools_en"] + a["files"]
    return (clamp(10 * min(1, k / 10)), f"{a['tools_en']} calculators in {LANG_NAME[MAIN_LANG]}" + (f" ({a['tools_ar']} in {OTHER_LANGS[0]['name'] if len(OTHER_LANGS) == 1 else 'other languages'})" if OTHER_LANGS else "")
            + f" and {a['files']} downloadable files; ten earn full marks.")


def r_valid(c, q, g, sm):
    v = q["valid"]
    if not v["nodes"]:
        return None
    w = v["why"]
    return (clamp(10 * v["score"]), f"{round(100 * v['score'])}% of {v['nodes']} structured-data items pass their checks"
            + (f"; most common gap: {w[0][0]} ({w[0][1]})." if w else "."))


def r_brand(c, q, g, sm):
    b = q["brand"]
    if not b["forms"]:
        return None
    others = [f"{k} {v}" for k, v in b["forms"][1:3]]
    v = 10 * (0.7 * b["top_share"] + 0.3 * b["site_name"] / max(1, b["n"]))
    return (clamp(v), f"'{b['top']}' is {round(100 * b['top_share'])}% of brand mentions" + (f" (also {', '.join(others)})" if others else "")
            + f"; site name set on {b['site_name']} of {b['n']} pages. Off-site profiles keep the {AW} score.", 0.7)


def r_nap(c, q, g, sm):
    p = q["nap"]
    n = p["n"] or 1
    ph = p["phone_pages"] / n * (1 if len(p["phones"]) <= 1 else 0.5)
    ad = p["addr_pages"] / n * (1 if p["addr_forms"] <= 1 else 0.5)
    li = min(1, p["licence_pages"] / n * 2)
    return (clamp(10 * (0.4 * ph + 0.4 * ad + 0.2 * li)),
            f"Phone on {p['phone_pages']} of {n} pages ({pl(len(p['phones']), 'number')}); structured-data address on {p.get('addr_any', 0)} pages, "
            f"with a street or city on {p['addr_pages']}; {CFG.get('licence_label', 'trade licence number')} on {p['licence_pages']}. The Google listing keeps the {AW} score.", 0.75)


def r_social(c, q, g, sm):
    s = q["social"]
    return (clamp(2.5 * len(s)), f"Home page links {pl(len(s), 'social profile')}" + (f": {', '.join(s)}." if s else "."))


def r_refdom(c, q, g, sm):
    if not sm or not sm.get("monthly"):
        return None
    m = sm["monthly"][-1]
    good = sum(1 for _, a in sm.get("top_domains", []) if a >= 20)
    v = 0.5 * min(10, m["score"] / 4) + 0.5 * min(10, good / 2)
    return (clamp(v), f"Authority score {m['score']} of 100; {good} of {m['domains']} referring domains score 20 or more "
            f"(strongest {max((a for _, a in sm.get('top_domains', [])), default=0)}).", 1.0, f"Semrush, read {sm.get('read', '')}")


def r_answer(c, q, g, sm):
    a = q["answer"]
    if not a["n"]:
        return None
    return (clamp(10 * a["pass"] / a["n"]), f"{a['pass']} of {a['n']} guides, service and tool pages open with a 12 to 60 word answer after the H1.")


def r_facts(c, q, g, sm):
    f = q["facts"]
    if not f["n"]:
        return None
    return (clamp(10 * f["score"]), f"Of {f['n']} guides, {f['nums']} give three or more figures, {f['cited']} cite a source and {f['dated']} show a date.")


def r_clarity(c, q, g, sm):
    k = q["clarity"]
    if not k["found"]:
        return 0.0, "No Organization node in the home page structured data."
    return (clamp(10 * len(k["have"]) / k["of"]), f"Home page organisation node has {len(k['have'])} of {k['of']} fields"
            + (f"; missing {', '.join(k['miss'])}." if k["miss"] else "."))


def r_consist(c, q, g, sm):
    k = q["consist"]
    share = (k["checks"] - k["off_n"]) / k["checks"] if k["checks"] else 1.0
    v = 10 * share - (k["phones"] - 1) * 1.0 * (k["phones"] > 1) - (k["emails"] - 1) * 1.0 * (k["emails"] > 1)
    tax = (f"{k['checks'] - k['off_n']} of {k['checks']} VAT and corporate tax rates match 5% and 9%"
           + (f" ({k['off'][0][1]} on {k['off'][0][0]})" if k["off"] else "") + "; ") if k["checks"] else ""
    return clamp(v), tax + f"{pl(k['phones'], 'phone number')} and {pl(k['emails'], 'email address')} across the site."


def r_cited(c, q, g, sm):
    a = g.get("ai")
    if a is None:
        return None
    top = ", ".join(f"{k} {int(v)}" for k, v in sorted(a["sources"].items(), key=lambda kv: -kv[1])[:3])
    return (clamp(a["sessions"] / 5), f"{int(a['sessions'])} visits from AI assistants in the last 28 days" + (f" ({top})" if top else "")
            + "; 50 earn full marks.")


def r_snippet(c, q, g, sm):
    s = q["snippet"]
    if not s["n"]:
        return None
    return (clamp(10 * s["score"]), f"{s['qa']} of {s['n']} guides, service and tool pages carry FAQ markup or question headings; "
            f"{q['answer']['pass']} open with a direct answer.")


def r_parity(c, q, g, sm):
    p = q.get("parity")
    if not p or not p["n"]:
        return None
    return (clamp(10 * p["score"]), f"{p['paired']} of {p['n']} English pages have an Arabic version; {len(p['en_only'])} English only"
            + (f"; shortest Arabic versions: {', '.join(f'{x[1]}%' for x in p['thin'][:3])} of the English length." if p["thin"] else "."))


def r_armeta(c, q, g, sm):
    a = q.get("armeta")
    if not a or not a["n"]:
        return None
    f = a["fails"]
    return (clamp(10 * a["score"]), f"{round(100 * a['score'])}% of title and description checks pass on {a['n']} Arabic pages"
            + (f"; most common gap: {f[0][0]} ({f[0][1]})." if f else "."))


def r_events(c, q, g, sm):
    ev = g.get("events")
    if ev is None:
        return None
    exp = ["page_view"] + [e for x in CFG.get("enquiries", []) for e in x["events"]]
    seen = [e for e in exp if ev["counts"].get(e, 0) > 0]
    ga = q["ga"]
    ids = sorted(ga["ids"], key=lambda i: -ga["ids"][i])
    tag = ga["pages"] / max(1, ga["n"]) * (1 if len(ids) <= 1 else 0.5) * (1 if "page_view" in seen else 0)
    parts = {"seen": (0.4, len(seen) / len(exp)), "tag": (0.3, tag)}
    if ev.get("key") is not None:
        parts["key"] = (0.3, 1.0 if "generate_lead" in ev["key"] else 0.0)
    w = sum(a for a, _ in parts.values())
    v = 10 * sum(a * b for a, b in parts.values()) / w
    miss = [e for e in exp if e not in seen]
    key_t = ("generate_lead is a key event" if ev.get("key") and "generate_lead" in ev["key"] else
             "generate_lead is not marked as a key event" if ev.get("key") is not None else f"key-event setting not readable, kept from the {AW}")
    return (clamp(v), f"{len(seen)} of {len(exp)} expected events recorded in 28 days" + (f" (none yet: {', '.join(miss)})" if miss else "")
            + f"; tag {', '.join(ids) or 'missing'} on {ga['pages']} of {ga['n']} pages; {key_t}.", round(w, 2))


def lang_rules():
    out = {}
    for x in OTHER_LANGS:
        code, name = x["code"], x["name"]

        def parity(c, q, g, sm, code=code, name=name):
            p = (q.get("lang") or {}).get(code)
            if not p or not p["n"]:
                return None
            an = "an" if name[0] in "AEIOU" else "a"
            return (clamp(10 * p["score"]), f"{p['paired']} of {p['n']} {LANG_NAME[MAIN_LANG]} pages have {an} {name} version; {len(p['en_only'])} without one"
                    + (f"; shortest: {', '.join(f'{t[1]}%' for t in p['thin'][:3])} of the {LANG_NAME[MAIN_LANG]} length." if p["thin"] else "."))

        def meta(c, q, g, sm, code=code, name=name):
            p = ((q.get("lang") or {}).get(code) or {}).get("meta")
            if not p or not p["n"]:
                return None
            f_ = p["fails"]
            return (clamp(10 * p["score"]), f"{round(100 * p['score'])}% of title and description checks pass on {p['n']} {name} pages"
                    + (f"; most common gap: {f_[0][0]} ({f_[0][1]})." if f_ else "."))

        def query(c, q, g, sm, code=code, name=name):
            t = (g.get("targets") or {}).get("langs", {}).get(code)
            if not t:
                return None
            return (clamp(10 * t["shown"] / t["total"]), f"{t['shown']} of {t['total']} {name} target searches showed the site in Google in the last 28 days.")
        out.update({f"parity_{code}": parity, f"meta_{code}": meta, f"query_{code}": query})

    def query_main(c, q, g, sm):
        t = (g.get("targets") or {}).get("langs", {}).get(MAIN_LANG)
        if not t:
            return None
        return (clamp(10 * t["shown"] / t["total"]), f"{t['shown']} of {t['total']} {LANG_NAME[MAIN_LANG]} target searches showed the site in Google in the last 28 days.")
    out[f"query_{MAIN_LANG}"] = query_main
    return out


def share(n, d):
    return n / d if d else 0


def r_medrev(c, q, g, sm):
    m = q.get("medical")
    if not m or not (m["cats"] + m["procs"]):
        return None
    n = m["cats"] + m["procs"]
    return clamp(10 * share(m["reviewed"], n)), f"A named medical reviewer on {m['reviewed']} of {n} treatment pages."


def r_accredit(c, q, g, sm):
    m = q.get("medical")
    if not m or not (m["cats"] + m["procs"]):
        return None
    n = m["cats"] + m["procs"]
    return clamp(10 * min(1, share(m["accredit"], n) * 2)), f"Clinic accreditation or licence named on {m['accredit']} of {n} treatment pages; half earns full marks."


def r_medsrc(c, q, g, sm):
    m = q.get("medical")
    if not m or not m["content"]:
        return None
    return clamp(10 * min(1, share(m["sourced"], m["content"]) / 0.6)), f"{m['sourced']} of {m['content']} treatment, guide and blog pages cite a medical or official source; 60% earns full marks."


def r_cost(c, q, g, sm):
    m = q.get("medical")
    if not m or not m["procs"]:
        return None
    return clamp(10 * share(m["priced"], m["procs"])), f"A price on {m['priced']} of {m['procs']} procedure pages."


def r_aftercare(c, q, g, sm):
    m = q.get("medical")
    if not m or not m["procs"]:
        return None
    v = 0.5 * share(m["aftercare"], m["procs"]) + 0.5 * share(m["risks"], m["procs"])
    return clamp(10 * v), f"Recovery covered under its own heading on {m['aftercare']} of {m['procs']} procedure pages; risks on {m['risks']}."


def r_pathway(c, q, g, sm):
    m = q.get("medical")
    if not m or not m["pathways"]:
        return None
    thin = [k for k, v in m["pathways"].items() if any(v.get(code, 0) < 5 for code in LANG_NAME)]
    return (clamp(10 * m["pathway_score"]), f"{len(m['pathways']) - len(thin)} of {len(m['pathways'])} treatment areas have five or more procedures in every language"
            + (f"; fewer in {', '.join(t.replace('-', ' ') for t in thin[:3])}." if thin else "."))


def r_medschema(c, q, g, sm):
    m = q.get("medical")
    if not m or not m["procs"]:
        return None
    return clamp(10 * share(m["schema"], m["procs"])), f"Medical structured data (MedicalProcedure or MedicalWebPage) on {m['schema']} of {m['procs']} procedure pages."


def r_dupes(c, q, g, sm):
    a = q.get("agency")
    if not a or not a["industries"]:
        return None
    v = 0.6 * (1 - share(a["near_dup"], a["industries"])) + 0.4 * min(1, a["uniq_median"] / 0.5)
    return (clamp(10 * v), f"{a['near_dup']} of {a['industries']} industry pages are near copies of another; a median {round(100 * a['uniq_median'])}% "
            f"of each page's wording appears on no other industry page (half earns full marks).")


def r_proof(c, q, g, sm):
    a = q.get("agency")
    if not a:
        return None
    return (clamp(2 * a["proof_external"]), f"{a['proof_external']} client stories from outside clients; {a['proof_own']} of the {a['proof']} portfolio pages show the group's own sites. Five earn full marks.")


def r_demo(c, q, g, sm):
    a = q.get("agency")
    if not a or not a["products"]:
        return None
    return clamp(10 * share(a["demo"], a["products"])), f"A live demo on {a['demo']} of {a['products']} product pages."


def r_pricing(c, q, g, sm):
    a = q.get("agency")
    if not a:
        return None
    v = 10 if a["pricing_page"] else 6 if a["priced"] else 0
    return float(v), ("A pricing page is published." if a["pricing_page"] else f"Prices on {a['priced']} of {a['products']} product pages; no pricing page." if a["priced"] else "No pricing page and no prices on product pages.")


def r_markets(c, q, g, sm):
    a = q.get("agency")
    if not a or not a["markets"]:
        return None
    have = [k for k, v in a["markets"].items() if v]
    miss = [k for k, v in a["markets"].items() if not v]
    return (clamp(10 * share(len(have), len(a["markets"]))), f"{len(have)} of {len(a['markets'])} markets have their own landing page"
            + (f"; none yet for {', '.join(miss)}." if miss else "."))


def r_compare(c, q, g, sm):
    a = q.get("agency")
    if not a:
        return None
    return clamp(10 * min(1, a["compare"] / 3)), f"{a['compare']} comparison or alternatives pages; three earn full marks."


RULES = {"crawl": r_crawl, "intent": r_intent, "cluster": r_cluster, "depth": r_depth, "eeat": r_eeat, "assets": r_assets,
         "valid": r_valid, "brand": r_brand, "nap": r_nap, "social": r_social, "refdom": r_refdom, "answer": r_answer,
         "facts": r_facts, "clarity": r_clarity, "consist": r_consist, "cited": r_cited, "snippet": r_snippet,
         "parity": r_parity, "armeta": r_armeta, "events": r_events,
         "medrev": r_medrev, "accredit": r_accredit, "medsrc": r_medsrc, "cost": r_cost, "aftercare": r_aftercare, "pathway": r_pathway,
         "medschema": r_medschema, "dupes": r_dupes, "proof": r_proof, "demo": r_demo, "pricing": r_pricing, "markets": r_markets,
         "compare": r_compare, **lang_rules()}


def fill_baseline(cube, measured, day):
    """Subs with no audit score take the first measured reading; unmeasured ones keep their judged score.
    Returns True when the cube changed and should be saved."""
    open_ = [s for b in cube["blocks"] for s in b["subs"] if s.get("audit") is None]
    if not open_:
        return False
    for s in open_:
        m = measured.get(s["auto"]) if s["auto"] else None
        s["audit"] = round(m[0], 1) if m else s.get("judged", 0.0)
    if cube.get("audit_overall") is None:
        cube["audit_overall"] = round(sum(b["weight"] * sum(x["weight"] * x["audit"] for x in b["subs"]) / sum(x["weight"] for x in b["subs"])
                                          for b in cube["blocks"]) / 100, 2)
    cube["audit_date"] = cube.get("audit_date") or day.isoformat()
    return True


def stage_of(cube, day):
    for i, s in enumerate(cube["stages"]):
        if s["until"] is None or day <= dt.date.fromisoformat(s["until"]):
            return i, s
    return len(cube["stages"]) - 1, cube["stages"][-1]


def score(cube, measured, day):
    si, stage = stage_of(cube, day)
    ad = dt.date.fromisoformat(cube["audit_date"])
    AUDIT_SRC = f"{cube.get('audit_label', 'Audit')}, {ad.strftime('%b')} {ad.day}"
    blocks, overall = [], 0.0
    for b in cube["blocks"]:
        subs = []
        for s in b["subs"]:
            m = measured.get(s["auto"]) if s["auto"] else None
            part = (m[2] if len(m) > 2 else 1.0) if m else 0.0
            sc = round(part * m[0] + (1 - part) * s["audit"], 2) if m else s["audit"]
            src = (m[3] if len(m) > 3 else "Measured daily" if part >= 1 else f"Measured daily, {round(100 * (1 - part))}% {AW}") if m else AUDIT_SRC
            subs.append({**s, "score": sc, "source": src, "measured": bool(m), "part": part, "rule": m[0] if m else None,
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
