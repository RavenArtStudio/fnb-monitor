"""Page-level checks behind the content, entity, GEO and Arabic sub-metrics of the cube (Checkpoint 28).

The crawl feeds each page through Doc once; site_quality() then turns the pages into the facts the
cube scores. Every rule is fixed and stated beside its check, so a score traces back to the pages
behind it. Nothing here calls the network.
"""
import json
import re
import statistics
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
ORG_TYPES = {"Organization", "LocalBusiness", "ProfessionalService", "AccountingService", "FinancialService", "Corporation"}
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
            "words": words(main), "ga": sorted(set(re.findall(r"\bG-[A-Z0-9]{6,12}\b", html))), "ld_bad": bad}


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
        name = re.sub(r"\b(uae|vat|kpi|qsr|fnb|f&b)\b", lambda m: {"fnb": "FnB", "f&b": "F&B"}.get(m.group(1).lower(), m.group(1).upper()), name, flags=re.I)
    return name + (", Arabic" if ar else "")


# ---------------------------------------------------------------- text rules
BYLINE = re.compile(r"^\s*(by|written by|reviewed by|بقلم|كتبه|إعداد|كتابة|مراجعة)\s+\S", re.I)
DATED = re.compile(r"\b(updated|last updated|published|reviewed)\b|تحديث|آخر تحديث|نُشر|تاريخ النشر|"
                   r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2},? 20\d\d\b|\b\d{1,2} (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]* 20\d\d\b|\b20\d\d-\d\d-\d\d\b", re.I)
NUMBER = re.compile(r"(?:AED|Dh|USD|US\$|\$|درهم)\s?\d[\d,.]*|\d[\d,.]*\s?(?:%|AED|dirhams?|درهم|days|months|years|hours|يوم|أيام|شهر|أشهر|سنة|سنوات)|\b\d{1,3}(?:,\d{3})+\b", re.I)
QWORD = re.compile(r"[?؟]\s*$")
CRED = re.compile(r"\b(CMA|CIA|ACCA|CPA|ACA|FCA|CFA|CA|Chartered|Certified)\b|\b\d{1,2}\+?\s+years\b|\d{1,2}\+?\s+(عاماً|عامًا|عاما|سنة|سنوات)", re.I)
LICENCE = re.compile(r"(trade\s+licen[cs]e|licen[cs]e\s+(no|number|#)|رخصة\s+تجارية|رقم\s+الرخصة)[^0-9\n]{0,25}[0-9٠-٩]{3,}", re.I)
OTHER_GCC = re.compile(r"saudi|ksa|oman|bahrain|qatar|kuwait|egypt|السعودية|عمان|عُمان|البحرين|قطر|الكويت|مصر", re.I)
MNE = re.compile(r"multinational|\bmne|pillar|dmtt|top-up|global minimum|متعددة الجنسيات|الحد الأدنى العالمي", re.I)
VAT_PCT = re.compile(r"(\bVAT\b|ضريبة القيمة المضافة|القيمة المضافة)(?P<gap>[^%٪\d٠-٩.\n]{0,40}?)(?P<num>[\d٠-٩]{1,3}(?:[.٫][\d٠-٩]+)?)\s?[%٪]", re.I)
CT_PCT = re.compile(r"(\bcorporate\s+(?:income\s+)?tax\b|ضريبة الشركات|ضريبة دخل الشركات)(?P<gap>[^%٪\d٠-٩.\n]{0,40}?)(?P<num>[\d٠-٩]{1,3}(?:[.٫][\d٠-٩]+)?)\s?[%٪]", re.I)
OTHER_TAX = re.compile(r"corporate|income tax|excise|withholding|customs|ضريبة الشركات|الانتقائية|الجمارك|القيمة المضافة|\bVAT\b", re.I)
BRAND = re.compile(r"\bF\s*(?:&|and|n)\s*B\s+Performance\b", re.I)
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


def pct_hits(rx, text):
    """Rates written right after a tax name; skipped when another tax is named in between."""
    out = []
    for m in rx.finditer(text):
        if OTHER_TAX.search(m.group("gap")):
            continue
        v = float(m.group("num").translate(AR_DIGITS))
        ctx = text[max(0, m.start() - 80): m.end() + 80]
        out.append((v, ctx))
    return out


# ---------------------------------------------------------------- structured-data rules
REQ = {"Organization": ["name", "url"], "LocalBusiness": ["name", "address"], "ProfessionalService": ["name", "address"],
       "AccountingService": ["name", "address"], "FinancialService": ["name", "address"], "WebSite": ["name", "url"],
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
    lang = lambda o: "ar" if (o.get("lang") or "").startswith("ar") else "en"
    for o in ok:
        o["_flat"] = flat(o.get("_body", ""))
        o["types"] = sorted({t for n in o.get("_nodes", []) for t in types(n)})
    arts = [o for o in live if set(o["types"]) & ART_TYPES]
    svc = [o for o in live if re.search(r"/services/[^/]+$", o["u"])]
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
        en = sum(1 for o in live if lang(o) == "en" and match(o, c["en"]))
        ar = sum(1 for o in live if lang(o) == "ar" and match(o, c["ar"]))
        cl.append({"name": c["name"], "en": en, "ar": ar, "score": round(min(1, en / 3) * 0.6 + min(1, ar / 3) * 0.4, 3)})
    q["clusters"] = cl

    # depth: median words of the guides, by language.
    med = lambda xs: statistics.median(xs) if xs else 0
    q["depth"] = {"en_n": sum(1 for o in arts if lang(o) == "en"), "ar_n": sum(1 for o in arts if lang(o) == "ar"),
                  "en_med": round(med([o["words"] for o in arts if lang(o) == "en"])),
                  "ar_med": round(med([o["words"] for o in arts if lang(o) == "ar"]))}

    # eeat: bylines (guides and service pages), dated guides, guides citing sources, credentials on About.
    about = byp.get("/ae/about") or next((o for o in ok if o["u"].rstrip("/").endswith("/about") and lang(o) == "en"), None)
    creds = sorted({m.group(0).strip() for m in CRED.finditer(about.get("_main", ""))}) if about else []
    q["eeat"] = {"arts": len(arts), "svc": len(svc), "by_art": sum(1 for o in arts if o["byline"]),
                 "by_svc": sum(1 for o in svc if o["byline"]), "dated": sum(1 for o in arts if o["dated"] and o["dated_ld"]),
                 "cited": sum(1 for o in arts if o["ext"]), "creds": creds[:8], "about": bool(about),
                 "uncited": [o["u"] for o in arts if not o["ext"]]}

    # assets: calculators and downloads.
    files = sorted({urlparse(urljoin(site + o["u"], h)).path for o in ok for h, _ in o.get("links_all", [])
                    if urlparse(urljoin(site + o["u"], h)).path.lower().rsplit(".", 1)[-1] in FILE_EXT
                    and host(urljoin(site + o["u"], h)) == host(site)})
    q["assets"] = {"tools_en": sum(1 for o in tools if lang(o) == "en"), "tools_ar": sum(1 for o in tools if lang(o) == "ar"),
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
            a = n.get("address")
            for x in (a if isinstance(a, list) else [a]):
                if isinstance(x, dict) and (x.get("streetAddress") or x.get("addressLocality")):
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
                "addr_pages": sum(1 for o in ok if o["has_addr"]), "addr_forms": len(addrs), "licence_pages": lic, "emails": emails}

    # social: profiles linked from the home page (sameAs and links).
    home = byp.get("/ae") or (ok[0] if ok else {})
    nets = set()
    for n in home.get("_nodes", []):
        sa = n.get("sameAs")
        for u in (sa if isinstance(sa, list) else [sa] if isinstance(sa, str) else []):
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
    for o in live:
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

    # parity and armeta: Arabic versions of the English pages.
    en_pages = [o for o in live if lang(o) == "en"]
    par, en_only, thin = [], [], []
    for o in en_pages:
        p = pair(o)
        if p is None:
            par.append(0.0)
            en_only.append(o["u"])
            continue
        r = p["words"] / o["words"] if o["words"] else 1.0
        par.append(min(1.0, r / 0.85))
        if r < 0.6:
            thin.append([o["u"], round(100 * r)])
    q["parity"] = {"n": len(en_pages), "score": round(sum(par) / len(par), 4) if par else 0, "en_only": en_only,
                   "thin": sorted(thin, key=lambda x: x[1])[:8], "paired": len(en_pages) - len(en_only)}
    ar_pages = [o for o in live if lang(o) == "ar"]
    titles = [o.get("title") for o in ok]
    descs = [o.get("desc") for o in ok]
    passed, total, fails = 0, 0, {}
    for o in ar_pages:
        p = pair(o)
        for kind, val, lo, hi, pool in (("title", o.get("title") or "", 20, 70, titles), ("description", o.get("desc") or "", 60, 170, descs)):
            tests = {f"{kind} not mainly Arabic": ar_share(val) >= 0.5, f"{kind} length": lo <= len(val) <= hi,
                     f"{kind} not unique": bool(val) and pool.count(val) == 1,
                     f"{kind} same as English": not (p is not None and val and val == (p.get("title") if kind == "title" else p.get("desc")))}
            for k, okk in tests.items():
                total += 1
                passed += okk
                if not okk:
                    fails.setdefault(k, []).append(o["u"])
    q["armeta"] = {"n": len(ar_pages), "score": round(passed / total, 4) if total else 0,
                   "fails": sorted(([k, len(v), v[:3]] for k, v in fails.items()), key=lambda x: -x[1])[:6]}

    # crawl: robots, sitemap in robots, and every listed page indexable.
    q["indexable"] = {"n": len(ok), "noindex": [o["u"] for o in ok if o.get("noindex")],
                      "blocked": [o["u"] for o in ok if not robots_allowed(o["u"])]}

    # ga: the analytics tag on every page.
    ids = {}
    for o in ok:
        for i in o.get("ga", []):
            ids[i] = ids.get(i, 0) + 1
    q["ga"] = {"ids": ids, "pages": sum(1 for o in ok if o.get("ga")), "n": len(ok)}
    return q


def page_rows(ok):
    """Compact per-page record written to data/pages.json, for checking the rules against the site."""
    keep = ("u", "lang", "status", "noindex", "title", "desc", "h1t", "words", "types", "ext", "byline", "dated", "nums",
            "answer", "first_w", "first", "qheads", "faq", "ga", "site_name")
    return [{k: o.get(k) for k in keep if k in o} for o in ok]
