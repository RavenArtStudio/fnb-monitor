"""Page-level checks behind the content, entity, GEO and Arabic sub-metrics of the cube (Checkpoint 28).

The crawl feeds each page through Doc once; site_quality() then turns the pages into the facts the
cube scores. Every rule is fixed and stated beside its check, so a score traces back to the pages
behind it. Nothing here calls the network.
"""
import json
import re
import zlib
import statistics

import siteconf
from siteconf import CFG, MAIN_LANG, OTHER_LANGS, LANG_NAME
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

SKIP = {"script", "style", "noscript", "template", "svg", "title"}
BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "br", "tr", "td", "th", "dd", "dt",
         "summary", "details", "header", "footer", "nav", "aside", "main", "figcaption", "blockquote", "ul", "ol",
         "table", "form", "label", "button", "span", "a", "strong", "em", "small", "time"}
INLINE = {"span", "a", "strong", "em", "small", "time"}
SUMMARY_CLASS = re.compile(r"(^|[\s_-])(summary|tldr|tl-dr|takeaways?|key-points|quick-answer|answer-box|short-answer)($|[\s_-])", re.I)
SOCIAL = {"linkedin.com": "LinkedIn", "instagram.com": "Instagram", "facebook.com": "Facebook", "x.com": "X",
          "twitter.com": "X", "youtube.com": "YouTube", "tiktok.com": "TikTok", "threads.net": "Threads", "pinterest.com": "Pinterest"}
FILE_EXT = ("pdf", "xlsx", "xls", "csv", "docx", "doc", "zip", "pptx")
ORG_TYPES = {"Organization", "LocalBusiness", "ProfessionalService", "AccountingService", "FinancialService", "Corporation",
             "MedicalBusiness", "MedicalOrganization", "MedicalClinic", "Hospital", "TravelAgency"}
ART_TYPES = {"Article", "BlogPosting", "NewsArticle", "TechArticle", "Report"}
AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")


class Doc(HTMLParser):
    """Visible text of the whole page and of <main>, headings, paragraphs after the H1, links and JSON-LD."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip, self.main, self.saw_main, self.saw_h1 = 0, 0, False, False
        self.body, self.mtext, self.h1, self.heads, self.paras, self.links, self.ld = [], [], [], [], [], [], []
        self.cur_h, self.in_p, self.in_ld, self.site_name, self.summary = None, None, False, "", 0

    def _close_p(self):
        if self.in_p is not None:
            t = norm_ws("".join(self.in_p))
            if t:
                self.paras.append(t)
            self.in_p = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script" and (a.get("type") or "").lower() == "application/ld+json":
            self.in_ld = True
            self.ld.append("")
        if tag in SKIP:
            self.skip += 1
            return
        if tag == "meta" and (a.get("property") or "").lower() == "og:site_name":
            self.site_name = (a.get("content") or "").strip()
        if tag == "main":
            self.main += 1
            self.saw_main = True
        if self.main and SUMMARY_CLASS.search(a.get("class") or ""):
            self.summary += 1
        if tag in ("h1", "h2", "h3"):
            self._close_p()
            self.cur_h = (tag, [])
        if tag == "p" and (self.main or not self.saw_main):
            self._close_p()
            if self.saw_h1:
                self.in_p = []
        if tag == "a" and a.get("href"):
            self.links.append((a["href"], self.main > 0))
        if tag in BLOCK and tag not in INLINE:
            self._sep()

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_ld = False
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if tag == "main":
            self.main = max(0, self.main - 1)
        if tag == "p":
            self._close_p()
        if self.cur_h and tag == self.cur_h[0]:
            t = norm_ws("".join(self.cur_h[1]))
            if tag == "h1":
                self.h1.append(t)
                self.saw_h1 = True
            else:
                self.heads.append(t)
            self.cur_h = None
        if tag in BLOCK and tag not in INLINE:
            self._sep()

    def _sep(self):
        self.body.append("\n")
        if self.main:
            self.mtext.append("\n")

    def handle_data(self, d):
        if self.in_ld:
            self.ld[-1] += d
            return
        if self.skip:
            return
        self.body.append(d)
        if self.main:
            self.mtext.append(d)
        if self.cur_h:
            self.cur_h[1].append(d)
        if self.in_p is not None:
            self.in_p.append(d)


def norm_ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def flat(s):
    """Lower case, letters and digits only, single spaces: for 'is this text on the page' checks."""
    s = (s or "").translate(AR_DIGITS).lower().replace("’", "'")
    s = re.sub(r"[ً-ْٰـ]", "", s)
    return re.sub(r"[^\w&]+", " ", s).strip()


def words(s):
    return len(re.findall(r"\w+", s or ""))


def ar_share(s):
    letters = re.findall(r"[^\W\d_]", s or "")
    return sum(1 for ch in letters if "؀" <= ch <= "ۿ") / len(letters) if letters else 0.0


def ld_nodes(blocks):
    out, bad = [], 0
    for raw in blocks:
        try:
            x = json.loads(raw)
        except Exception:
            bad += 1
            continue
        items = x if isinstance(x, list) else [x]
        for it in items:
            if isinstance(it, dict) and isinstance(it.get("@graph"), list):
                out += [n for n in it["@graph"] if isinstance(n, dict)]
            elif isinstance(it, dict):
                out.append(it)
    return out, bad


def types(n):
    t = n.get("@type")
    return set(t) if isinstance(t, list) else {t} if t else set()


def walk_type(x, t):
    """Every object of @type t anywhere in a JSON-LD tree."""
    if isinstance(x, list):
        for y in x:
            yield from walk_type(y, t)
    elif isinstance(x, dict):
        if t in types(x):
            yield x
        for v in x.values():
            yield from walk_type(v, t)


def walk_key(x, k):
    """Every value of key k anywhere in a JSON-LD tree."""
    if isinstance(x, list):
        for y in x:
            yield from walk_key(y, k)
    elif isinstance(x, dict):
        if k in x:
            yield x[k]
        for v in x.values():
            yield from walk_key(v, k)


def page_doc(html):
    """Everything the quality rules need from one page. Keys starting with '_' stay in memory only."""
    d = Doc()
    try:
        d.feed(html)
        d.close()
    except Exception:
        pass
    d._close_p()
    body = norm_ws("".join(d.body))
    main = norm_ws("".join(d.mtext)) if d.saw_main else body
    nodes, bad = ld_nodes(d.ld)
    return {"_body": body, "_main": main, "_nodes": nodes, "h1t": d.h1[0] if d.h1 else "", "heads": d.heads[:40],
            "paras": d.paras[:12], "links_all": d.links, "site_name": d.site_name, "summary": d.summary,
            "words": words(main), "ga": sorted(set(re.findall(r"\bG-[A-Z0-9]{6,12}\b", html))), "ld_bad": bad,
            "demo": bool(re.search(r"ai-agents\.js|voice[-_ ]?widget|chat[-_ ]?widget|data-demo", html, re.I))}


def page_name(path):
    """'/ae/ar/tools/vat-calculator' -> 'Vat calculator, Arabic'; language segments come from the site config."""
    p = (path or "/").split("?")[0].rstrip("/")
    home = (CFG.get("home") or "/").rstrip("/")
    if home and home != "/":
        p = re.sub("^" + re.escape(home) + "(?=/|$)", "", p)
    lang = None
    for x in OTHER_LANGS:
        if re.match(rf"^/{x['code']}(/|$)", p):
            lang, p = x["name"], re.sub(rf"^/{x['code']}(?=/|$)", "", p)
            break
    if p in ("", "/"):
        name = "Home"
    else:
        name = p.strip("/").split("/")[-1].replace("-", " ")
        name = name[:1].upper() + name[1:]
        up = "|".join(re.escape(w) for w in CFG.get("upcase", []) + ["fnb", "f&b"])
        name = re.sub(rf"\b({up})\b", lambda m: {"fnb": "FnB", "f&b": "F&B"}.get(m.group(1).lower(), m.group(1).upper()), name, flags=re.I)
        pl_ = "|".join(re.escape(w) for w in CFG.get("places", []))
        if pl_:
            name = re.sub(rf"\b({pl_})\b", lambda m: m.group(1).title(), name, flags=re.I)
    return name + (f", {lang}" if lang else "")


# ---------------------------------------------------------------- text rules
BYLINE = re.compile(r"^\s*(by|written by|reviewed by|بقلم|كتبه|إعداد|كتابة|مراجعة)\s+\S", re.I)
DATED = re.compile(r"\b(updated|last updated|published|reviewed)\b|تحديث|آخر تحديث|نُشر|تاريخ النشر|"
                   r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2},? 20\d\d\b|\b\d{1,2} (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]* 20\d\d\b|\b20\d\d-\d\d-\d\d\b", re.I)
NUMBER = re.compile(r"(?:AED|Dh|USD|US\$|\$|درهم)\s?\d[\d,.]*|\d[\d,.]*\s?(?:%|AED|dirhams?|درهم|days|months|years|hours|يوم|أيام|شهر|أشهر|سنة|سنوات)|\b\d{1,3}(?:,\d{3})+\b", re.I)
QWORD = re.compile(r"[?؟]\s*$")
CRED = re.compile(CFG.get("cred_re") or r"\b(CMA|CIA|ACCA|CPA|ACA|FCA|CFA|CA|Chartered|Certified)\b|\b\d{1,2}\+?\s+years\b|\d{1,2}\+?\s+(عاماً|عامًا|عاما|سنة|سنوات)", re.I)
LICENCE = re.compile(CFG.get("licence_re") or r"(trade\s+licen[cs]e|licen[cs]e\s+(no|number|#)|رخصة\s+تجارية|رقم\s+الرخصة)[^0-9\n]{0,25}[0-9٠-٩]{3,}", re.I)
TAX_CHECKS = CFG.get("tax_checks", False)
OTHER_GCC = re.compile(r"saudi|ksa|oman|bahrain|qatar|kuwait|egypt|السعودية|عمان|عُمان|البحرين|قطر|الكويت|مصر", re.I)
MNE = re.compile(r"multinational|\bmne|pillar|dmtt|top-up|global minimum|متعددة الجنسيات|الحد الأدنى العالمي", re.I)
VAT_PCT = re.compile(r"(\bVAT\b|ضريبة القيمة المضافة|القيمة المضافة)(?P<gap>[^%٪\d٠-٩.\n]{0,40}?)(?P<num>[\d٠-٩]{1,3}(?:[.٫][\d٠-٩]+)?)\s?[%٪]", re.I)
CT_PCT = re.compile(r"(\bcorporate\s+(?:income\s+)?tax\b|ضريبة الشركات|ضريبة دخل الشركات)(?P<gap>[^%٪\d٠-٩.\n]{0,40}?)(?P<num>[\d٠-٩]{1,3}(?:[.٫][\d٠-٩]+)?)\s?[%٪]", re.I)
OTHER_TAX = re.compile(r"corporate|income tax|excise|withholding|customs|ضريبة الشركات|الانتقائية|الجمارك|القيمة المضافة|\bVAT\b", re.I)
BRAND = re.compile(CFG.get("brand_re") or r"\bF\s*(?:&|and|n)\s*B\s+Performance\b", re.I)
NOT_SOURCE = re.compile(r"maps\.|/maps|goo\.gl|g\.page|wa\.me|whatsapp|calendly", re.I)
AI_SOURCES = re.compile(r"chatgpt|openai|perplexity|gemini|bard\.google|copilot|claude|anthropic|you\.com|phind|deepseek|meta\.ai|grok|mistral|poe\.com", re.I)

EN_STOP = {"for", "in", "the", "of", "and", "a", "an", "to", "on", "with", "your"}
AR_STOP = {"في", "من", "على", "عن", "الى", "إلى", "و", "مع"}


SAME = {"accountant": "accounting", "accountants": "accounting", "bookkeeper": "bookkeeping", "bookkeepers": "bookkeeping",
        "مطعم": "مطاعم", "محاسب": "محاسب", "خدمه": "خدمات"}
OPTIONAL = {"dubai", "uae", "emirates", "abu", "dhabi", "sharjah", "service", "best", "دبي", "امارات", "خدمات", "ظبي", "ابو", "شارقه"}


def en_stem(t):
    t = SAME.get(t, t)
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


def ar_norm(t):
    t = re.sub(r"[ً-ْٰـ]", "", t)
    t = re.sub("[أإآ]", "ا", t).replace("ة", "ه").replace("ى", "ي")
    for pre in ("وال", "بال", "كال", "فال", "لل", "ال"):
        if t.startswith(pre) and len(t) - len(pre) >= 2:
            t = t[len(pre):]
            break
    if len(t) > 3 and t.endswith("ه"):
        t = t[:-1]
    return SAME.get(t, t)


def tokens(s):
    out = []
    for t in re.findall(r"[\w&]+", (s or "").lower().translate(AR_DIGITS)):
        if re.search(r"[؀-ۿ]", t):
            if t not in AR_STOP:
                out.append(ar_norm(t))
        elif t not in EN_STOP:
            out.append(en_stem(t))
    return out


def first_answer(paras):
    """First real paragraph after the H1: skips bylines, date lines and short labels."""
    for p in paras:
        w = words(p)
        if BYLINE.search(p) or (DATED.search(p) and w < 25) or w < 8:
            continue
        return p, w
    return "", 0


def host(u):
    h = urlparse(u).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def social_of(u):
    h = host(u)
    for k, v in SOCIAL.items():
        if h == k or h.endswith("." + k):
            return v
    return None


def phone_key(s):
    d = re.sub(r"\D", "", (s or "").translate(AR_DIGITS))
    d = d[2:] if d.startswith("00") else d
    d = d[3:] if d.startswith("971") else d
    return d.lstrip("0") or None


PRICE_QUAL = re.compile(r"(before|after|excl\.?|excluding|incl\.?|including|plus|ex|net of|قبل|بعد|شامل|غير شامل|بدون)\s*$", re.I)


def pct_hits(rx, text):
    """Rates written right after a tax name; skipped when another tax is named in between, or when the tax name
    only qualifies a price ('AED 20 before VAT is 20.8%')."""
    out = []
    for m in rx.finditer(text):
        if OTHER_TAX.search(m.group("gap")) or PRICE_QUAL.search(text[max(0, m.start() - 14): m.start()]):
            continue
        v = float(m.group("num").translate(AR_DIGITS))
        ctx = text[max(0, m.start() - 80): m.end() + 80]
        out.append((v, ctx))
    return out


# ---------------------------------------------------------------- structured-data rules
REQ = {"Organization": ["name", "url"], "LocalBusiness": ["name", "address"], "ProfessionalService": ["name", "address"],
       "AccountingService": ["name", "address"], "FinancialService": ["name", "address"], "WebSite": ["name", "url"],
       "MedicalBusiness": ["name", "address"], "MedicalClinic": ["name", "address"], "MedicalOrganization": ["name", "url"],
       "MedicalProcedure": ["name"], "MedicalWebPage": ["name|headline|url"],
       "WebPage": ["name|headline|url"], "AboutPage": ["name|url"], "ContactPage": ["name|url"], "CollectionPage": ["name|url"],
       "FAQPage": ["mainEntity"], "BreadcrumbList": ["itemListElement"], "WebApplication": ["name", "applicationCategory"],
       "SoftwareApplication": ["name", "applicationCategory"], "Service": ["name", "provider"], "Person": ["name"],
       "HowTo": ["name", "step"], "ItemList": ["itemListElement"], "Product": ["name"], "Event": ["name", "startDate"],
       **{t: ["headline", "author", "datePublished"] for t in ART_TYPES}}


def has(n, spec):
    return any(n.get(k) not in (None, "", [], {}) for k in spec.split("|"))


def node_check(n, page, body_flat):
    """Returns (value 0..1, reason or '') for one top-level JSON-LD node."""
    ts = types(n)
    req = [r for t in ts for r in REQ.get(t, [])] or ["name|@id|url|headline"]
    miss = [r.split("|")[0] for r in req if not has(n, r)]
    if miss:
        return 0.0, f"{'/'.join(sorted(ts)) or 'Untyped'} missing {', '.join(miss)}"
    if ts & ART_TYPES:
        a = n.get("author")
        a = a if isinstance(a, list) else [a]
        if not any(isinstance(x, dict) and x.get("name") or isinstance(x, str) and x for x in a):
            return 0.0, "Article author has no name"
        ht = set(tokens(n.get("headline")))
        pt = set(tokens(page.get("title"))) | set(tokens(page.get("h1t")))
        if ht and len(ht & pt) / len(ht) < 0.8:
            return 0.0, "Article headline differs from the title and H1"
    if "FAQPage" in ts:
        qs = n.get("mainEntity")
        qs = qs if isinstance(qs, list) else [qs]
        good = [q for q in qs if isinstance(q, dict) and q.get("name")
                and isinstance(q.get("acceptedAnswer"), dict) and q["acceptedAnswer"].get("text")]
        if not good or len(good) < len(qs):
            return 0.0, "FAQ question without a name or answer"
        vis = sum(1 for q in good if flat(q["name"]) in body_flat)
        return vis / len(good), ("" if vis == len(good) else "FAQ questions in the markup but not on the page")
    if "BreadcrumbList" in ts:
        items = n.get("itemListElement") or []
        items = items if isinstance(items, list) else [items]
        if any(not (isinstance(i, dict) and i.get("position") and (i.get("name") or isinstance(i.get("item"), dict))) for i in items):
            return 0.0, "Breadcrumb item without position or name"
    return 1.0, ""


# ---------------------------------------------------------------- the site
def site_quality(ok, site, cfg, targets, robots_allowed):
    """ok: crawled 200 pages (dicts from the crawl, with page_doc() keys). Returns aggregates and per-page flags."""
    byp = {o["u"].rstrip("/") or "/": o for o in ok}
    live = [o for o in ok if not o.get("noindex")]
    lang = lambda o: siteconf.lang_of(o.get("lang"))
    for o in ok:
        o["_flat"] = flat(o.get("_body", ""))
        o["types"] = sorted({t for n in o.get("_nodes", []) for t in types(n)})
    arts = [o for o in live if set(o["types"]) & ART_TYPES]
    svc = [o for o in live if re.search(CFG.get("service_re", r"/services/[^/]+$"), o["u"])]
    tools = [o for o in live if {"WebApplication", "SoftwareApplication"} & set(o["types"])]
    content = {o["u"]: o for o in arts + svc + tools}.values()
    q = {}

    # Pairs: an English page and its Arabic version through hreflang.
    def pair(o):
        for a in o.get("alts", []):
            p = byp.get(a.rstrip("/") or "/")
            if p is not None and p is not o and lang(p) != lang(o):
                return p
        return None

    # Author names: every Article author, both scripts.
    authors = set()
    for o in arts:
        for n in o["_nodes"]:
            if types(n) & ART_TYPES:
                a = n.get("author")
                for x in (a if isinstance(a, list) else [a]):
                    nm = x.get("name") if isinstance(x, dict) else x if isinstance(x, str) else None
                    if nm:
                        authors.add(flat(nm))
    def external(o):
        return sorted({host(urljoin(site + o["u"], h)) for h, in_main in o.get("links_all", []) if in_main
                       and urljoin(site + o["u"], h).startswith("http") and host(urljoin(site + o["u"], h)) not in ("", host(site))
                       and not social_of(urljoin(site + o["u"], h)) and not NOT_SOURCE.search(h)})
    for o in live:
        o["ext"] = external(o)
        mf = flat(o.get("_main", ""))
        o["byline"] = any(BYLINE.search(p) for p in o.get("paras", [])[:6]) or any(a and a in mf for a in authors)
        o["dated"] = bool(DATED.search(o.get("_main", "")))
        o["dated_ld"] = any(n.get("dateModified") for n in o["_nodes"] if types(n) & ART_TYPES)
        o["nums"] = len(set(m.group(0) for m in NUMBER.finditer(o.get("_main", "").translate(AR_DIGITS))))
        fa, fw = first_answer(o.get("paras", []))
        o["answer"] = bool(o.get("summary")) or 12 <= fw <= 60
        o["first"] = fa[:160]
        o["first_w"] = fw
        o["qheads"] = sum(1 for h in o.get("heads", []) if QWORD.search(h))
        o["faq"] = "FAQPage" in o["types"]

    # intent: each target search needs one page whose title and H1 carry all of its topic words
    # (place names and the word 'services' are optional).
    rows = []
    for tq in targets:
        tt = set(tokens(tq)) - OPTIONAL or set(tokens(tq))
        best, where = 0.0, None
        for o in live:
            pt = set(tokens(o.get("title"))) | set(tokens(o.get("h1t")))
            cov = len(tt & pt) / len(tt) if tt else 0
            if cov > best:
                best, where = cov, o["u"]
        rows.append([tq, round(best, 2), where])
    q["intent"] = {"total": len(rows), "pass": sum(1 for r in rows if r[1] >= 1), "rows": rows}

    # cluster: pages per topic, by language (title and H1).
    cl = []
    for c in cfg.get("clusters", []):
        def match(o, kws):
            s = flat((o.get("title") or "") + " " + (o.get("h1t") or ""))
            return any(flat(k) in s for k in kws)
        cnt = {code: sum(1 for o in live if lang(o) == code and match(o, c.get(code, []))) for code in LANG_NAME}
        others = [code for code in LANG_NAME if code != MAIN_LANG]
        sc_ = min(1, cnt[MAIN_LANG] / 3) * (0.6 if others else 1) + sum(min(1, cnt[k] / 3) * 0.4 / len(others) for k in others)
        cl.append({"name": c["name"], **cnt, "counts": cnt, "score": round(sc_, 3)})
    q["clusters"] = cl

    # depth: median words of the guides (or, where the site sells from its service pages, of guides and service pages), by language.
    med = lambda xs: statistics.median(xs) if xs else 0
    deep = list({o["u"]: o for o in arts + svc}.values()) if CFG.get("depth_pages") == "content" else arts
    q["depth"] = {"langs": {code: {"n": sum(1 for o in deep if lang(o) == code), "med": round(med([o["words"] for o in deep if lang(o) == code]))}
                            for code in LANG_NAME}}
    q["depth"].update(en_n=q["depth"]["langs"][MAIN_LANG]["n"], en_med=q["depth"]["langs"][MAIN_LANG]["med"],
                      ar_n=q["depth"]["langs"].get("ar", {}).get("n", 0), ar_med=q["depth"]["langs"].get("ar", {}).get("med", 0))

    # eeat: bylines (guides and service pages), dated guides, guides citing sources, credentials on About.
    about = byp.get((CFG.get("about") or "/about").rstrip("/")) or next((o for o in ok if o["u"].rstrip("/").endswith("/about") and lang(o) == MAIN_LANG), None)
    creds = sorted({m.group(0).strip() for m in CRED.finditer(about.get("_main", ""))}) if about else []
    q["eeat"] = {"arts": len(arts), "svc": len(svc), "by_art": sum(1 for o in arts if o["byline"]),
                 "by_svc": sum(1 for o in svc if o["byline"]), "dated": sum(1 for o in arts if o["dated"] and o["dated_ld"]),
                 "cited": sum(1 for o in arts if o["ext"]), "creds": creds[:8], "about": bool(about),
                 "uncited": [o["u"] for o in arts if not o["ext"]]}

    # assets: calculators and downloads.
    files = sorted({urlparse(urljoin(site + o["u"], h)).path for o in ok for h, _ in o.get("links_all", [])
                    if urlparse(urljoin(site + o["u"], h)).path.lower().rsplit(".", 1)[-1] in FILE_EXT
                    and host(urljoin(site + o["u"], h)) == host(site)})
    q["assets"] = {"tools_en": sum(1 for o in tools if lang(o) == MAIN_LANG), "tools_ar": sum(1 for o in tools if lang(o) != MAIN_LANG),
                   "files": len(files)}

    # valid: required properties per type, headline match, FAQ questions on the page.
    vals, why = [], {}
    for o in ok:
        for n in o["_nodes"]:
            v, r = node_check(n, o, o["_flat"])
            vals.append(v)
            if r:
                why.setdefault(r, []).append(o["u"])
    q["valid"] = {"nodes": len(vals), "score": round(sum(vals) / len(vals), 4) if vals else 0,
                  "bad": sum(1 for o in ok if o.get("ld_bad")),
                  "why": sorted(([k, len(v), v[:3]] for k, v in why.items()), key=lambda x: -x[1])[:6]}

    # brand: one written form of the name; og:site_name.
    forms = {}
    for o in ok:
        for m in BRAND.finditer(o.get("_body", "")):
            k = norm_ws(m.group(0))
            forms[k] = forms.get(k, 0) + 1
    top = max(forms.items(), key=lambda kv: kv[1]) if forms else ("", 0)
    sn = {}
    for o in ok:
        sn[o.get("site_name") or ""] = sn.get(o.get("site_name") or "", 0) + 1
    q["brand"] = {"forms": sorted(forms.items(), key=lambda kv: -kv[1]), "top": top[0], "top_share": round(top[1] / sum(forms.values()), 4) if forms else 0,
                  "site_name": sum(v for k, v in sn.items() if k and k == top[0]), "site_name_empty": sn.get("", 0), "n": len(ok)}

    # nap: one phone, one address, a trade licence.
    phones, emails, addrs, lic = {}, {}, {}, 0
    for o in ok:
        ps, es, ad = set(), set(), set()
        for h, _ in o.get("links_all", []):
            if h.lower().startswith("tel:"):
                k = phone_key(h[4:])
                if k:
                    ps.add(k)
            if h.lower().startswith("mailto:"):
                es.add(h[7:].split("?")[0].strip().lower())
        for n in o["_nodes"]:
            if n.get("telephone"):
                k = phone_key(str(n["telephone"]))
                if k:
                    ps.add(k)
            if isinstance(n.get("email"), str):
                es.add(n["email"].replace("mailto:", "").strip().lower())
        for x in walk_type(o["_nodes"], "PostalAddress"):
            o["any_addr"] = True
            if x.get("streetAddress") or x.get("addressLocality"):
                digits = re.sub(r"\D", "", str(x.get("streetAddress", "")).translate(AR_DIGITS))
                ad.add(((x.get("addressCountry") if isinstance(x.get("addressCountry"), str) else "") or "", digits or flat(str(x.get("addressLocality", "")))))
        for k in ps:
            phones[k] = phones.get(k, 0) + 1
        for k in es:
            emails[k] = emails.get(k, 0) + 1
        for k in ad:
            addrs[k] = addrs.get(k, 0) + 1
        o["has_addr"] = bool(ad)
        if LICENCE.search(o.get("_body", "").translate(AR_DIGITS)):
            lic += 1
    q["nap"] = {"n": len(ok), "phones": phones, "phone_pages": max(phones.values(), default=0),
                "addr_pages": sum(1 for o in ok if o["has_addr"]), "addr_any": sum(1 for o in ok if o.get("any_addr")), "addr_forms": len(addrs), "licence_pages": lic, "emails": emails}

    # social: profiles linked from the home page (sameAs and links).
    home = byp.get((CFG.get("home") or "/").rstrip("/") or "/") or (ok[0] if ok else {})
    nets = set()
    for n in walk_key(home.get("_nodes", []), "sameAs"):
        for u in (n if isinstance(n, list) else [n] if isinstance(n, str) else []):
            if social_of(u):
                nets.add(social_of(u))
    for h, _ in home.get("links_all", []):
        if social_of(urljoin(site, h)):
            nets.add(social_of(urljoin(site, h)))
    q["social"] = sorted(nets)

    # answer and snippet: the first real paragraph is a direct answer; FAQ or question headings.
    cont = list(content)
    q["answer"] = {"n": len(cont), "pass": sum(1 for o in cont if o["answer"]),
                   "fail": [[o["u"], o["first_w"], o["first"][:90]] for o in cont if not o["answer"]][:8]}
    q["snippet"] = {"n": len(cont), "qa": sum(1 for o in cont if o["faq"] or o["qheads"] >= 2),
                    "score": round(sum(0.5 * (o["faq"] or o["qheads"] >= 2) + 0.5 * o["answer"] for o in cont) / len(cont), 4) if cont else 0}

    # facts: figures, a source and a date on each guide.
    q["facts"] = {"n": len(arts), "nums": sum(1 for o in arts if o["nums"] >= 3), "cited": sum(1 for o in arts if o["ext"]),
                  "dated": sum(1 for o in arts if o["dated"]),
                  "score": round(sum(0.4 * (o["nums"] >= 3) + 0.4 * bool(o["ext"]) + 0.2 * o["dated"] for o in arts) / len(arts), 4) if arts else 0}

    # clarity: fields on the home page organisation node.
    fields = ["@id", "name", "url", "logo", "description", "address", "telephone|contactPoint", "sameAs", "areaServed"]
    orgs = [n for n in home.get("_nodes", []) if types(n) & ORG_TYPES]
    best = max(orgs, key=lambda n: sum(has(n, f_) for f_ in fields), default=None)
    q["clarity"] = {"found": bool(best), "have": [f_.split("|")[0] for f_ in fields if best and has(best, f_)],
                    "miss": [f_.split("|")[0] for f_ in fields if not (best and has(best, f_))], "of": len(fields)}

    # consist: VAT and corporate tax rates, one phone, one email.
    checks, off = 0, []
    for o in (live if TAX_CHECKS else []):
        txt = o.get("_body", "")
        for v, ctx in pct_hits(VAT_PCT, txt):
            if OTHER_GCC.search(ctx):
                continue
            checks += 1
            if v not in (0, 5):
                off.append([o["u"], f"VAT {v:g}%", norm_ws(ctx)[:120]])
        for v, ctx in pct_hits(CT_PCT, txt):
            if OTHER_GCC.search(ctx):
                continue
            checks += 1
            if v not in (0, 9) and not (v == 15 and MNE.search(ctx)):
                off.append([o["u"], f"Corporate tax {v:g}%", norm_ws(ctx)[:120]])
    q["consist"] = {"checks": checks, "off": off[:8], "off_n": len(off), "phones": len(phones), "emails": len(emails)}

    # parity and metadata: each other-language version of the main-language pages (hreflang pairs).
    main_pages = [o for o in live if lang(o) == MAIN_LANG]
    titles = [o.get("title") for o in ok]
    descs = [o.get("desc") for o in ok]

    def pair_in(o, code):
        for a_ in o.get("alts", []):
            p_ = byp.get(a_.rstrip("/") or "/")
            if p_ is not None and p_ is not o and lang(p_) == code:
                return p_
        return None
    q["lang"] = {}
    for x in OTHER_LANGS:
        code = x["code"]
        par, en_only, thin = [], [], []
        for o in main_pages:
            p_ = pair_in(o, code)
            if p_ is None:
                par.append(0.0)
                en_only.append(o["u"])
                continue
            r = p_["words"] / o["words"] if o["words"] else 1.0
            par.append(min(1.0, r / 0.85))
            if r < 0.6:
                thin.append([o["u"], round(100 * r)])
        lq = {"n": len(main_pages), "score": round(sum(par) / len(par), 4) if par else 0, "en_only": en_only,
              "thin": sorted(thin, key=lambda t_: t_[1])[:8], "paired": len(main_pages) - len(en_only)}
        pages_l = [o for o in live if lang(o) == code]
        back = {}
        for m in main_pages:
            t_ = pair_in(m, code)
            if t_ is not None:
                back.setdefault(id(t_), m)
        passed, total, fails = 0, 0, {}
        for o in pages_l:
            p_ = back.get(id(o))
            for kind, val, lo, hi, pool in (("title", o.get("title") or "", 20, 70, titles), ("description", o.get("desc") or "", 60, 170, descs)):
                tests = {f"{kind} not mainly {x['name']}": in_language(val, code), f"{kind} length": lo <= len(val) <= hi,
                         f"{kind} not unique": bool(val) and pool.count(val) == 1,
                         f"{kind} same as {LANG_NAME[MAIN_LANG]}": not (p_ is not None and val and val == (p_.get("title") if kind == "title" else p_.get("desc")))}
                for k_, okk in tests.items():
                    total += 1
                    passed += okk
                    if not okk:
                        fails.setdefault(k_, []).append(o["u"])
        lq["meta"] = {"n": len(pages_l), "score": round(passed / total, 4) if total else 0,
                      "fails": sorted(([k_, len(v), v[:3]] for k_, v in fails.items()), key=lambda t_: -t_[1])[:6]}
        q["lang"][code] = lq
    if "ar" in q["lang"]:                 # FNB's Arabic sub-metrics read these names
        q["parity"] = {k_: v for k_, v in q["lang"]["ar"].items() if k_ != "meta"}
        q["armeta"] = q["lang"]["ar"]["meta"]

    # crawl: robots, sitemap in robots, and every listed page indexable.
    q["indexable"] = {"n": len(ok), "noindex": [o["u"] for o in ok if o.get("noindex")],
                      "blocked": [o["u"] for o in ok if not robots_allowed(o["u"])]}

    # Checks that belong to one kind of business (Checkpoint 30), switched on in sites/<id>.json.
    if "medical" in CFG.get("checks", []):
        q["medical"] = medical_checks(live, lang, site)
    if "agency" in CFG.get("checks", []):
        q["agency"] = agency_checks(ok, live, lang, site)

    # ga: the analytics tag on every page.
    ids = {}
    for o in ok:
        for i in o.get("ga", []):
            ids[i] = ids.get(i, 0) + 1
    q["ga"] = {"ids": ids, "pages": sum(1 for o in ok if o.get("ga")), "n": len(ok)}
    return q


MED_REVIEW = re.compile(r"medically reviewed|medical review(er)?|reviewed by (dr|prof)|clinical(ly)? reviewed|medizinisch geprüft|ärztlich geprüft|"
                        r"geprüft von (dr|prof)|مراجعة طبية|راجعه (د|الدكتور)", re.I)
ACCREDIT = re.compile(r"\bJCI\b|joint commission|ISO 9001|ISO 15189|ministry of health|sağlık bakanlığı|USHA[ŞS]|health tourism (authori[sz]ation|certificate|licen[cs]e)|"
                      r"TEMOS|accredit|akkreditiert|zertifiziert|معتمد|اعتماد|وزارة الصحة", re.I)
MED_SOURCE = re.compile(r"(^|\.)(nhs\.uk|who\.int|nih\.gov|cdc\.gov|mayoclinic\.org|clevelandclinic\.org|bmj\.com|thelancet\.com|nejm\.org|"
                        r"aaos\.org|ada\.org|plasticsurgery\.org|ishrs\.org|asmbs\.org|eshre\.eu|aao\.org|entnet\.org|auanet\.org|uroweb\.org|"
                        r"saglik\.gov\.tr|cochrane\.org|europepmc\.org)$|\.gov(\.[a-z]{2})?$|\.edu$|\.ac\.uk$", re.I)
PRICE = re.compile(r"(€|EUR|£|GBP|\$|USD|AED|SAR)\s?\d[\d.,]{1,}|\d[\d.,]{2,}\s?(€|EUR|£|GBP|USD|AED|SAR)", re.I)
AFTER = re.compile(r"recovery|aftercare|after (the )?(surgery|treatment|procedure)|healing|nachsorge|erholung|heilung|التعافي|ما بعد|الرعاية بعد", re.I)
RISKS = re.compile(r"risk|complication|side effect|risiken|komplikation|nebenwirkung|مخاطر|مضاعفات|الآثار الجانبية", re.I)


def medical_checks(live, lang, site):
    """Treatment pages of a medical-travel site: who reviewed them, what backs them, and whether a patient can plan from them."""
    m = CFG.get("medical", {})
    cat_re, proc_re = re.compile(m.get("category_re", r"^/treatments/[^/]+$")), re.compile(m.get("procedure_re", r"^/treatments/[^/]+/procedures/[^/]+$"))
    strip = lambda u: re.sub(r"^/(" + "|".join(x["code"] for x in OTHER_LANGS) + r")(?=/)", "", u) if OTHER_LANGS else u
    mains = [o for o in live if lang(o) == MAIN_LANG]
    cats = [o for o in mains if cat_re.match(o["u"])]
    procs = [o for o in mains if proc_re.match(o["u"])]
    treat = cats + procs
    content = treat + [o for o in mains if re.match(r"^/(guides|blog)/", o["u"])]
    has_src = lambda o: any(MED_SOURCE.search(h) for h in o.get("ext", []))
    out = {"cats": len(cats), "procs": len(procs),
           "reviewed": sum(1 for o in treat if MED_REVIEW.search(o.get("_main", "")) or "reviewedBy" in json.dumps(o.get("_nodes", []))),
           "accredit": sum(1 for o in treat if ACCREDIT.search(o.get("_main", ""))),
           "sourced": sum(1 for o in content if has_src(o)), "content": len(content),
           "priced": sum(1 for o in procs if PRICE.search(o.get("_main", ""))),
           "aftercare": sum(1 for o in procs if any(AFTER.search(h) for h in o.get("heads", []))),
           "risks": sum(1 for o in procs if any(RISKS.search(h) for h in o.get("heads", []))),
           "schema": sum(1 for o in procs if {"MedicalProcedure", "MedicalWebPage", "MedicalCondition", "MedicalTherapy"} & set(o.get("types", [])))}
    per = {}
    for o in live:
        u = strip(o["u"])
        if proc_re.match(u):
            c_ = u.split("/")[2]
            per.setdefault(c_, {}).setdefault(lang(o), 0)
            per[c_][lang(o)] += 1
    out["pathways"] = {c_: v for c_, v in sorted(per.items())}
    langs = list(LANG_NAME)
    out["pathway_score"] = round(sum(min(1, v.get(code, 0) / 5) for v in per.values() for code in langs) / (len(per) * len(langs)), 4) if per else 0
    out["no_review"] = [o["u"] for o in treat if not (MED_REVIEW.search(o.get("_main", "")))][:3]
    return out


def shingles(text, k=5, keep=8):
    """Five-word shingles, sampled: only those whose checksum falls in one of `keep` buckets. The same shingle is kept or
    dropped on every page, so Jaccard similarity is estimated without its cost on long pages (first live run, 20 Nov 2026)."""
    w = re.findall(r"\w+", (text or "").lower())
    out = set()
    for i in range(max(0, len(w) - k + 1)):
        g = " ".join(w[i:i + k])
        if zlib.crc32(g.encode()) % keep == 0:
            out.add(g)
    return out


def agency_checks(ok, live, lang, site):
    """A service business selling to other businesses: industry pages that say something different, proof, demos, prices, markets."""
    a = CFG.get("agency", {})
    ind_re = re.compile(a.get("industry_re", r"^/industries/[^/]+$"))
    prod_re = re.compile(a.get("product_re", r"^/products/[^/]+$"))
    proof_re = re.compile(a.get("proof_re", r"^/(portfolio|client-stories|case-studies)/[^/]+$"))
    ind = [o for o in live if ind_re.match(o["u"])]
    sh = {o["u"]: shingles(o.get("_main", "")) for o in ind}
    seen = {}                                   # shingle -> number of industry pages that use it
    for v in sh.values():
        for g in v:
            seen[g] = seen.get(g, 0) + 1
    dup, uniq = [], []
    us = list(sh)
    for i, u in enumerate(us):
        best, a_ = 0.0, sh[u]
        for j in range(len(us)):
            b_ = sh[us[j]]
            if i == j or not a_ or not b_:
                continue
            inter = len(a_ & b_) if len(a_) <= len(b_) else len(b_ & a_)
            best = max(best, inter / (len(a_) + len(b_) - inter))
            if best >= 0.6:
                break
        if best >= 0.6:
            dup.append(u)
        uniq.append(sum(1 for g in a_ if seen[g] == 1) / len(a_) if a_ else 0)
    own = [b.lower() for b in CFG.get("own_brands", [])]
    proof = [o for o in live if proof_re.match(o["u"])]
    external = [o for o in proof if not any(b in ((o.get("title") or "") + " " + o["u"].replace("-", " ")).lower() for b in own)]
    prods = [o for o in live if prod_re.match(o["u"])]
    pricing_page = any(re.search(r"pric", o["u"]) for o in live)
    priced = sum(1 for o in prods if PRICE.search(o.get("_main", "")))
    mk = a.get("market_pages", {})
    has_market = {c_: any(any(re.search(rf"(^|[-/]){re.escape(t)}([-/]|$)", o["u"]) for t in toks) for o in live) for c_, toks in mk.items()}
    compare = [o for o in live if re.search(r"(^|[-/])(vs|versus|alternatives?|compare|comparison)([-/]|$)", o["u"])]
    return {"industries": len(ind), "near_dup": len(dup), "uniq_median": round(statistics.median(uniq), 3) if uniq else 0,
            "dup_sample": dup[:3], "proof": len(proof), "proof_external": len(external), "proof_own": len(proof) - len(external),
            "products": len(prods), "demo": sum(1 for o in prods if o.get("demo")), "pricing_page": pricing_page, "priced": priced,
            "markets": has_market, "compare": len(compare)}


DE_WORDS = {"und", "der", "die", "das", "für", "mit", "in", "ihre", "sie", "wie", "was", "zu", "von", "bei", "nach", "türkei", "behandlung",
            "kosten", "klinik", "ein", "eine", "ist", "im", "auf", "oder", "ihr", "wir", "zahn", "haar", "operation", "ablauf"}


def in_language(text, code):
    """Is this title or description written in that language? Arabic by script; German by its common words or letters."""
    if not text:
        return False
    if code == "ar":
        return ar_share(text) >= 0.5
    if code == "de":
        toks = set(re.findall(r"\w+", text.lower()))
        return bool(toks & DE_WORDS) or bool(re.search(r"[äöüß]", text.lower()))
    return True


def page_rows(ok):
    """Compact per-page record written to data/pages.json, for checking the rules against the site."""
    keep = ("u", "lang", "status", "noindex", "title", "desc", "h1t", "words", "types", "ext", "byline", "dated", "nums",
            "answer", "first_w", "first", "qheads", "faq", "ga", "site_name")
    return [{k: o.get(k) for k in keep if k in o} for o in ok]
