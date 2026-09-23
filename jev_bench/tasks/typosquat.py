"""Typosquat second stage: noul "is the candidate a deliberate impersonation of the popular target?".

Positives (label True): real malicious package names from OSV MAL-* advisories (npm + PyPI) that sit
within Damerau-Levenshtein distance 2, a confusable-skeleton match, or a single-token affix of a
top-1000 package in the same ecosystem. The name, target and advisory are real; README, publisher and
downloads are synthesized (the packages are gone from the registries) and listed in meta.synthetic_fields.
Negatives (label False): real, live, legitimately-related packages (plugins, typings, ESM builds, forks,
wrappers) found through the npm search API, the ecosyste.ms top list and the PyPI JSON API, with their
real description/README excerpt, maintainers, first-publish date and weekly downloads.
Hard cases: positives with a rewritten README and an aged publisher; negatives whose README is the
target's own description (ESM builds, typings, forks).

Everything downloaded is cached under data/typosquat/. build(n, seed) is deterministic given the cache.
"""
import concurrent.futures as cf
import datetime as dt
import io
import json
import os
import random
import re
import time
import zipfile

import httpx

from . import Item, cache_path, write_items

NAME = "typosquat"
QKEY = "impersonation"
QUESTION = {"impersonation": {"type": "noul", "instructions": "Is the candidate package a deliberate impersonation of the popular target package (trying to be mistaken for it), rather than an honest plugin, fork, wrapper, or typing package?",
          "criteria": {"true": "pretends to be the target: copied README, throwaway publisher, no distinct purpose", "false": "honest related package: distinct purpose, established publisher, clearly named as an extension or fork"}}}

TOP_N = 1000
OSV_URLS = {"npm": "https://osv-vulnerabilities.storage.googleapis.com/npm/all.zip",
            "PyPI": "https://osv-vulnerabilities.storage.googleapis.com/PyPI/all.zip"}
UA = {"User-Agent": "jev-bench/0.1 (+https://github.com/brandonrc/jev-bench)"}
_RANK = {"confusable": 0, "edit1": 1, "edit2": 2, "affix": 3}

# ----------------------------------------------------------------------------- http helpers
def _get(url, retries=4, timeout=30):
    for i in range(retries):
        try:
            r = httpx.get(url, headers=UA, timeout=timeout, follow_redirects=True)
            if r.status_code == 404:
                return None
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(1.5 * (i + 1)); continue
            r.raise_for_status(); return r
        except (httpx.TransportError, httpx.HTTPStatusError):
            time.sleep(1.5 * (i + 1))
    return None

def _get_json(url):
    r = _get(url)
    if r is None: return None
    try: return r.json()
    except ValueError: return None

def _cached_json(filename, producer):
    p = cache_path(NAME, filename)
    if os.path.exists(p):
        with open(p) as f: return json.load(f)
    data = producer()
    with open(p, "w") as f: json.dump(data, f)
    return data

def _pmap(fn, xs, workers=6):
    with cf.ThreadPoolExecutor(workers) as ex:
        return list(ex.map(fn, xs))

# ----------------------------------------------------------------------------- name relations
_CONF = [("0", "o"), ("1", "l"), ("i", "l"), ("rn", "m"), ("vv", "w"), ("5", "s"), ("3", "e")]
def _skeleton(s):
    s = s.lower()
    for a, b in _CONF: s = s.replace(a, b)
    return s

def _osa(a, b):
    from rapidfuzz.distance import OSA
    return OSA.distance(a, b)

_SEP = "-_."
def _bare(n):
    return n.split("/", 1)[1] if n.startswith("@") and "/" in n else n

def _affix_core(cb):
    """Strings left after stripping one single-token affix from cb (candidates for a target name)."""
    out = set()
    for sep in _SEP:
        i = cb.find(sep); j = cb.rfind(sep)
        if i > 0:
            head, rest = cb[:i], cb[i + 1:]
            if rest and re.fullmatch(r"[a-z0-9]+", head) and len(head) <= 12: out.add(rest)      # prefix affix: "py-requests" -> requests
        if j > 0:
            rest, tail = cb[:j], cb[j + 1:]
            if rest and re.fullmatch(r"[a-z0-9]+", tail) and len(tail) <= 12: out.add(rest)      # suffix affix: "lodash-es" -> lodash
    m = re.fullmatch(r"(.+?)\d{1,2}", cb)
    if m: out.add(m.group(1))                                                                    # "urllib3" style
    if cb.startswith("py") and len(cb) > 4: out.add(cb[2:])
    if cb.endswith("js") and len(cb) > 4: out.add(cb[:-2])
    return out

def relation(cand, target):
    """'edit1'|'edit2'|'confusable'|'affix' or None. Never matches identical names."""
    c, t = cand.lower(), target.lower()
    cb = _bare(c)
    if c == t: return None
    if cb == t: return "affix" if c.startswith("@") else None  # scoped re-publish, e.g. @types/lodash
    if len(t) >= 4 and _skeleton(cb) == _skeleton(t): return "confusable"
    if len(t) >= 4:
        d = _osa(cb, t)
        if d == 1: return "edit1"
        if d == 2 and len(t) >= 6: return "edit2"
    if t in _affix_core(cb): return "affix"
    return None

def best_target(cand, tnames, tset, skel):
    """Fastest matching of one candidate against many targets. Returns (target, relation) or None."""
    c = cand.lower(); cb = _bare(c)
    if cb in tset:
        return (cb, "affix") if c.startswith("@") else None
    sk = _skeleton(cb)
    if len(cb) >= 4 and sk in skel and skel[sk] != cb: return (skel[sk], "confusable")
    from rapidfuzz import process
    from rapidfuzz.distance import OSA
    hit = process.extractOne(cb, tnames, scorer=OSA.distance, score_cutoff=2)
    if hit:
        t, d, _ = hit
        if len(t) >= 4 and d == 1: return (t, "edit1")
        if len(t) >= 6 and d == 2: return (t, "edit2")
    for core in _affix_core(cb):
        if core in tset: return (core, "affix")
    return None

# ----------------------------------------------------------------------------- data sources
_FALLBACK_NPM = ["lodash", "react", "express", "axios", "chalk", "commander", "debug", "moment", "request", "async", "bluebird", "underscore",
                 "webpack", "babel-core", "typescript", "eslint", "prettier", "jest", "mocha", "vue", "angular", "jquery", "socket.io", "mongoose",
                 "redux", "next", "dotenv", "uuid", "yargs", "glob", "minimist", "semver", "colors", "cross-env", "nodemon", "pm2", "ws", "cors",
                 "body-parser", "passport", "jsonwebtoken", "bcrypt", "electron", "discord.js", "puppeteer", "cheerio", "node-fetch", "rxjs", "three", "d3"]
_FALLBACK_PYPI = ["boto3", "requests", "urllib3", "setuptools", "numpy", "pandas", "six", "python-dateutil", "pyyaml", "cryptography", "django",
                  "flask", "pytest", "colorama", "jinja2", "click", "pillow", "matplotlib", "scipy", "tensorflow", "torch", "sqlalchemy", "pydantic",
                  "httpx", "aiohttp", "beautifulsoup4", "lxml", "jellyfish", "paramiko", "psycopg2", "redis", "celery", "fastapi", "uvicorn", "black",
                  "mypy", "tqdm", "rich", "typer", "selenium", "scrapy", "openai", "transformers", "scikit-learn", "opencv-python", "pyjwt", "bcrypt", "discord.py"]

def _top_npm():
    def produce():
        out = []
        for page in range(1, 11):
            d = _get_json(f"https://packages.ecosyste.ms/api/v1/registries/npmjs.org/packages?sort=downloads&order=desc&per_page=100&page={page}")
            if not d: break
            out += [{"name": p["name"], "description": (p.get("description") or "")[:600], "downloads": p.get("downloads")} for p in d]
            time.sleep(0.3)
        return out or [{"name": n, "description": "", "downloads": None} for n in _FALLBACK_NPM]
    return _cached_json("top-npm-1000.json", produce)[:TOP_N]

def _top_pypi():
    def produce():
        d = _get_json("https://raw.githubusercontent.com/hugovk/top-pypi-packages/main/top-pypi-packages.min.json")
        rows = [r["project"] for r in d["rows"]] if d else _FALLBACK_PYPI
        return [{"name": n, "description": "", "downloads": None} for n in rows]
    return _cached_json("top-pypi.json", produce)[:TOP_N]

def _top_pypi_all():
    return _cached_json("top-pypi.json", lambda: [{"name": n} for n in _FALLBACK_PYPI])

def _pypi_info(name):
    d = _get_json(f"https://pypi.org/pypi/{name}/json")
    if not d: return None
    info, rels = d.get("info", {}), d.get("releases", {})
    times = [f["upload_time"] for fs in rels.values() for f in fs if f.get("upload_time")]
    urls = info.get("project_urls") or {}
    repo = next((u for k, u in urls.items() if "github.com" in (u or "")), None) or (info.get("home_page") or "")
    return {"name": info.get("name") or name, "summary": (info.get("summary") or "")[:300],
            "description": re.sub(r"\s+", " ", (info.get("description") or ""))[:600],
            "author": info.get("author") or info.get("maintainer") or (info.get("author_email") or "").split("<")[0].strip() or "unknown",
            "created": min(times) if times else None, "n_releases": len(rels), "repo": repo}

def _pypi_downloads(name):
    d = _get_json(f"https://pypistats.org/api/packages/{name.lower()}/recent")
    return (d or {}).get("data", {}).get("last_week")

def _npm_doc(name):
    d = _get_json(f"https://registry.npmjs.org/{name}")
    if not d: return None
    readme = re.sub(r"\s+", " ", d.get("readme") or "")[:600]
    repo = d.get("repository"); repo = repo.get("url", "") if isinstance(repo, dict) else (repo or "")
    return {"name": d.get("name", name), "description": (d.get("description") or "")[:300], "readme": readme,
            "created": (d.get("time") or {}).get("created"), "maintainers": [m.get("name") for m in d.get("maintainers", []) if isinstance(m, dict)],
            "n_versions": len(d.get("versions", {})), "repo": re.sub(r"^git\+|\.git$", "", repo)}

def _npm_downloads(name):
    d = _get_json(f"https://api.npmjs.org/downloads/point/last-week/{name}")
    return (d or {}).get("downloads")

def _mal_names():
    """{ecosystem: [{name, id}]} from OSV MAL-* advisories, cached. Downloads ~250 MB of zips once."""
    def produce():
        out = {}
        for eco, url in OSV_URLS.items():
            zp = cache_path(NAME, f"osv-{eco.lower()}.zip")
            if not os.path.exists(zp):
                with httpx.stream("GET", url, headers=UA, timeout=120, follow_redirects=True) as r, open(zp, "wb") as f:
                    for chunk in r.iter_bytes(1 << 20): f.write(chunk)
            seen, rows = set(), []
            with zipfile.ZipFile(zp) as z:
                for info in z.infolist():
                    if not info.filename.startswith("MAL-"): continue
                    try: adv = json.load(io.TextIOWrapper(z.open(info), encoding="utf-8"))
                    except Exception: continue
                    for a in adv.get("affected", []):
                        n = (a.get("package") or {}).get("name")
                        if n and n not in seen:
                            seen.add(n); rows.append({"name": n, "id": adv.get("id")})
            out[eco] = rows
        return out
    return _cached_json("mal-names.json", produce)

def _advisory_text(eco, ids):
    """{advisory_id: summary} for the given ids, read from the cached zip."""
    zp = cache_path(NAME, f"osv-{eco.lower()}.zip")
    out = {}
    if not os.path.exists(zp): return out
    want = set(ids)
    with zipfile.ZipFile(zp) as z:
        names = {n.split("/")[-1].rsplit(".", 1)[0]: n for n in z.namelist() if n.startswith("MAL-")}
        for aid in want:
            fn = names.get(aid)
            if not fn: continue
            try:
                adv = json.load(io.TextIOWrapper(z.open(fn), encoding="utf-8"))
                out[aid] = re.sub(r"\s+", " ", (adv.get("summary") or adv.get("details") or ""))[:200]
            except Exception:
                pass
    return out

# ----------------------------------------------------------------------------- pools
def _positive_pool():
    """Real MAL names related to a top-1000 target. Cached."""
    def produce():
        targets = {"npm": _top_npm(), "PyPI": _top_pypi()}
        mal = _mal_names()
        rows = []
        for eco, advs in mal.items():
            tnames = [t["name"].lower() for t in targets[eco]]
            tset = set(tnames)
            skel = {}
            for t in tnames: skel.setdefault(_skeleton(t), t)
            for adv in advs:
                n = adv["name"]
                if n.lower() in tset or _bare(n.lower()) in tset and not n.startswith("@"): continue  # compromised real package, not a squat
                hit = best_target(n, tnames, tset, skel)
                if hit:
                    rows.append({"name": n, "target": hit[0], "relation": hit[1], "ecosystem": eco, "advisory_id": adv["id"]})
            summaries = _advisory_text(eco, [r["advisory_id"] for r in rows if r["ecosystem"] == eco])
            for r in rows:
                if r["ecosystem"] == eco: r["advisory_summary"] = summaries.get(r["advisory_id"], "")
        return rows
    return _cached_json("positive-pool.json", produce)

_PYPI_SUFFIXES = ["types-{t}", "{t}-stubs", "{t}-cli", "{t}-utils", "{t}-plugin", "{t}-extras", "{t}-tools", "{t}-contrib", "pytest-{t}",
                  "django-{t}", "flask-{t}", "{t}-toolbelt", "{t}-mock", "{t}-cache", "{t}-async", "async-{t}", "{t}2", "{t}3"]
_HARD_NEG_HINTS = ("-es", "-esm", "@types/", "types-", "-lite", "-fork", "-compat", "-legacy", "-next", "-stubs", "-mirror", "-py3", "-slim")

def _negative_pool():
    """Real live related packages with real metadata. Cached."""
    def produce():
        rng = random.Random(1234)
        mal_set = {r["name"].lower() for eco in _mal_names().values() for r in eco}
        npm_t, pypi_t = _top_npm(), _top_pypi()
        npm_names = [t["name"].lower() for t in npm_t]; npm_set = set(npm_names)
        pypi_all = [t["name"].lower() for t in _top_pypi_all()]; pypi_set = set(t["name"].lower() for t in pypi_t)
        found = {}

        def add(n, target, eco, extra):
            key = (n.lower(), eco)
            if key in found or n.lower() in mal_set or n.lower() == target.lower(): return
            rel = relation(n, target)
            if not rel: return
            found[key] = {"name": n, "target": target, "ecosystem": eco, "relation": rel, **extra}

        # (a) top-1000 npm packages that are themselves near-names of another top-1000 package (react-dom, lodash-es, @types/node ...)
        tdesc_npm = {t["name"].lower(): t.get("description", "") for t in npm_t}
        skel = {}
        for t in npm_names: skel.setdefault(_skeleton(t), t)
        for t in npm_t:
            hit = best_target(t["name"], npm_names, npm_set, skel)
            if hit and hit[0] != t["name"].lower():
                add(t["name"], hit[0], "npm", {"description": t.get("description", ""), "target_description": tdesc_npm.get(hit[0], ""), "src": "npm-top"})
        # (b) npm registry search around ~300 sampled targets
        npm_pick = rng.sample(npm_t, min(320, len(npm_t)))
        def npm_search(t):
            d = _get_json(f"https://registry.npmjs.org/-/v1/search?text={t['name']}&size=20")
            return [(o["package"], t) for o in (d or {}).get("objects", [])]
        for hits in _pmap(npm_search, npm_pick):
            kept = 0
            for p, t in hits:
                if kept >= 4: break
                before = len(found)
                add(p["name"], t["name"], "npm", {"description": (p.get("description") or "")[:300], "publisher": (p.get("publisher") or {}).get("username", "unknown"),
                                                 "target_description": t.get("description", ""), "src": "npm-search"})
                kept += len(found) > before
        # (c) PyPI: names in the top-15000 list that are near-names of a top-1000 PyPI package
        pskel = {}
        for t in pypi_set: pskel.setdefault(_skeleton(t), t)
        pypi_names = sorted(pypi_set)
        for n in pypi_all:
            if n in pypi_set and n in pypi_names[:TOP_N]: pass
            hit = best_target(n, pypi_names, pypi_set, pskel)
            if hit and hit[0] != n:
                add(n, hit[0], "PyPI", {"src": "pypi-top"})
        # (d) PyPI affix probes around ~200 sampled targets
        pypi_pick = rng.sample(pypi_t, min(200, len(pypi_t)))
        def pypi_probe(t):
            out = []
            for pat in rng.sample(_PYPI_SUFFIXES, 6):
                n = pat.format(t=t["name"])
                if n.lower() in mal_set or not relation(n, t["name"]) or (n.lower(), "PyPI") in found: continue
                if _get(f"https://pypi.org/pypi/{n}/json") is not None: out.append((n, t["name"]))
                if len(out) >= 2: break
            return out
        for hits in _pmap(pypi_probe, pypi_pick):
            for n, t in hits: add(n, t, "PyPI", {"src": "pypi-probe"})

        rows = list(found.values())
        # enrich with real registry metadata
        def enrich(x):
            if x["ecosystem"] == "npm":
                doc = _npm_doc(x["name"]); dl = _npm_downloads(x["name"])
                if not doc: return None
                x.update({"readme": doc["readme"] or doc["description"] or x.get("description", ""), "description": x.get("description") or doc["description"],
                          "created": doc["created"], "maintainers": doc["maintainers"], "publisher": (doc["maintainers"] or [x.get("publisher", "unknown")])[0],
                          "n_versions": doc["n_versions"], "repo": doc["repo"], "weekly_downloads": dl, "downloads_real": dl is not None})
            else:
                info = _pypi_info(x["name"])
                if not info or not info["created"]: return None
                dl = _pypi_downloads(x["name"])
                x.update({"readme": info["description"] or info["summary"], "description": info["summary"], "publisher": info["author"],
                          "created": info["created"], "maintainers": [info["author"]], "n_versions": info["n_releases"], "repo": info["repo"],
                          "weekly_downloads": dl, "downloads_real": dl is not None})
            return x
        rows = [x for x in _pmap(enrich, rows) if x]
        # target descriptions for PyPI (for hard negatives and copied-README positives)
        need = sorted({x["target"] for x in rows if x["ecosystem"] == "PyPI" and not x.get("target_description")})
        infos = _pmap(_pypi_info, need)
        tdesc = {t: (i or {}).get("summary", "") for t, i in zip(need, infos)}
        for x in rows:
            if x["ecosystem"] == "PyPI": x["target_description"] = tdesc.get(x["target"], "")
        return rows
    return _cached_json("negative-pool.json", produce)

def _pypi_target_desc(targets):
    """{target: summary} for PyPI targets used by positives. Cached."""
    def produce():
        infos = _pmap(_pypi_info, targets)
        return {t: (i or {}).get("summary", "") for t, i in zip(targets, infos)}
    return _cached_json("pypi-target-desc.json", produce)

# ----------------------------------------------------------------------------- hardcoded known cases (pilot)
_HARDCODED = [  # (candidate, target, is_squat, ecosystem)
    ("python3-dateutil", "python-dateutil", True, "PyPI"), ("jeIlyfish", "jellyfish", True, "PyPI"), ("colourama", "colorama", True, "PyPI"),
    ("crossenv", "cross-env", True, "npm"), ("babelcli", "babel-cli", True, "npm"), ("mongose", "mongoose", True, "npm"),
    ("lodash-es", "lodash", False, "npm"), ("react-dom", "react", False, "npm"), ("@types/lodash", "lodash", False, "npm"),
    ("lodash.merge", "lodash", False, "npm"), ("express-session", "express", False, "npm"), ("vue-router", "vue", False, "npm"),
    ("requests-oauthlib", "requests", False, "PyPI"), ("djangorestframework", "django", False, "PyPI"), ("urllib3-future", "urllib3", False, "PyPI"),
    ("mongoose-paginate", "mongoose", False, "npm"), ("tensorflow-addons", "tensorflow", False, "PyPI"), ("electron-builder", "electron", False, "npm"),
    ("discord.js-light", "discord.js", False, "npm"), ("cross-spawn", "cross-env", False, "npm"), ("setuptools-scm", "setuptools", False, "PyPI"),
]

# ----------------------------------------------------------------------------- rendering
_README = {
    "copied": "{T} - {D} Install with `{I} {C}`. See the {T} docs for the full API.",
    "rewritten": "{C}: drop-in replacement for {T} with performance fixes and extra helpers. Fully compatible API. Install `{I} {C}`.",
}
_DEFAULT_DESC = "A modern utility library delivering modularity, performance and extras."

def _age_days(created):
    if not created: return None
    try:
        d = dt.datetime.fromisoformat(created.replace("Z", "+00:00"))
        if d.tzinfo is None: d = d.replace(tzinfo=dt.timezone.utc)
        return (dt.datetime.now(dt.timezone.utc) - d).days
    except ValueError:
        return None

def _publisher_real(x):
    age = _age_days(x.get("created")); yrs = f"{age // 365} years" if age and age >= 365 else (f"{age} days" if age is not None else "unknown age")
    m = x.get("maintainers") or [x.get("publisher", "unknown")]
    repo = x.get("repo") or "no linked repository"
    return f"{x.get('publisher') or m[0]} (first published {yrs} ago, {len(m)} maintainer(s), {x.get('n_versions', '?')} releases, repository {repo})"

def _publisher_fresh(rng):
    return f"user_{rng.randint(10000, 99999)} (account created {rng.randint(1, 14)} days ago, 1 published package, no linked repository, 0 GitHub stars)"

def _publisher_aged(rng, c):
    stem = re.sub(r"[^a-z0-9]", "", _bare(c).split("-")[0])[:10] or "pkg"
    return f"{stem}dev (account {rng.randint(2, 4)} years old, {rng.randint(3, 8)} published packages, repository github.com/{stem}dev/{_bare(c)}, {rng.randint(40, 300)} stars)"

def _item(cand, target, label, readme, publisher, downloads, meta):
    return Item(task=NAME, id=f"{cand}->{target}", label=label, meta=meta,
                state={"candidate_name": cand, "popular_target": target, "candidate_readme": readme, "publisher": publisher,
                       "weekly_downloads": downloads, "lexical_note": "flagged by Damerau-Levenshtein / confusable-skeleton / affix stage"})

def build(n: int = 1200, seed: int = 0) -> list[Item]:
    rng = random.Random(seed)
    pos_pool = _positive_pool(); neg_pool = _negative_pool()
    tdesc = {t["name"].lower(): t.get("description", "") for t in _top_npm()}
    for x in neg_pool:
        if x.get("target_description"): tdesc.setdefault(x["target"].lower(), x["target_description"])
    pypi_targets = sorted({p["target"] for p in pos_pool if p["ecosystem"] == "PyPI" and p["target"].lower() not in tdesc})
    if pypi_targets: tdesc.update({k.lower(): v for k, v in _pypi_target_desc(pypi_targets).items()})
    half = n // 2 if n > 0 else min(len(neg_pool), len(pos_pool))
    hard_frac = 0.15
    items = []

    # ---- positives: prefer confusable/edit1/edit2; cap affix at 35% of positives; balance ecosystems roughly
    # affix positives on very short/generic targets ("next", "async") are mostly dependency-confusion names, not impersonation
    pos_pool = [p for p in pos_pool if p["relation"] != "affix" or len(p["target"]) >= 6]
    # scoped MAL names (@org/x) are dependency-confusion or compromised-org packages, not impersonations of x's neighbour;
    # keep only the scoped re-publish case (@scope/<target>). edit2 on short targets is too loose to trust.
    pos_pool = [p for p in pos_pool if not p["name"].startswith("@") or _bare(p["name"]).lower() == p["target"].lower()]
    pos_pool = [p for p in pos_pool if p["relation"] != "edit2" or len(p["target"]) >= 7]
    by_rel = {r: [p for p in pos_pool if p["relation"] == r] for r in _RANK}
    for r in by_rel: rng.shuffle(by_rel[r])
    n_affix = min(len(by_rel["affix"]), int(half * 0.35))
    rest = by_rel["confusable"] + by_rel["edit1"] + by_rel["edit2"]; rng.shuffle(rest)
    picked = rest[: half - n_affix] + by_rel["affix"][:n_affix]
    if len(picked) < half: picked += by_rel["affix"][n_affix: n_affix + half - len(picked)]
    rng.shuffle(picked)
    n_hard_pos = int(len(picked) * hard_frac)
    for i, p in enumerate(picked):
        c, t = p["name"], p["target"]
        desc = tdesc.get(t.lower()) or _DEFAULT_DESC
        inst = "npm i" if p["ecosystem"] == "npm" else "pip install"
        hard = i < n_hard_pos
        style = "rewritten" if hard or rng.random() < 0.25 else "copied"
        readme = _README[style].format(C=c, T=t, D=desc, I=inst)
        pub = _publisher_aged(rng, c) if hard else _publisher_fresh(rng)
        dl = rng.randint(300, 4000) if hard else rng.randint(5, 300)
        items.append(_item(c, t, True, readme, pub, dl, {"source": "osv", "advisory_id": p["advisory_id"], "advisory_summary": p.get("advisory_summary", ""),
                                                        "ecosystem": p["ecosystem"], "relation": p["relation"], "hard": hard, "readme_style": style,
                                                        "synthetic_fields": ["candidate_readme", "publisher", "weekly_downloads"]}))

    # ---- negatives: real metadata; hard negatives get the target's own description as README
    _OK_SCOPES = ("@types/", "@babel/", "@jest/", "@vue/", "@angular/", "@nestjs/", "@aws-sdk/", "@octokit/", "@testing-library/", "@storybook/", "@eslint/", "@typescript-eslint/")
    def _ok_neg(x):
        n = x["name"].lower()
        if n.startswith("@") and _bare(n) == x["target"].lower() and not n.startswith(_OK_SCOPES): return False  # random scoped re-publish: ambiguous
        return bool(x.get("readme") or x.get("description"))
    negs = [x for x in neg_pool if _ok_neg(x)]; rng.shuffle(negs)
    n_neg = (n - len(items)) if n > 0 else len(negs)
    # keep ecosystems roughly balanced: at most 55% from either
    cap = int(n_neg * 0.55); picked_neg, per = [], {"npm": 0, "PyPI": 0}
    for x in negs:
        if per[x["ecosystem"]] >= cap: continue
        picked_neg.append(x); per[x["ecosystem"]] += 1
        if len(picked_neg) >= n_neg: break
    negs = picked_neg
    hard_cands = [x for x in negs if any(h in x["name"].lower() for h in _HARD_NEG_HINTS) and (x.get("target_description") or "")]
    rng.shuffle(hard_cands)
    hard_ids = {x["name"] for x in hard_cands[: int(len(negs) * hard_frac)]}
    for x in negs:
        hard = x["name"] in hard_ids
        readme = x["target_description"] if hard else (x.get("readme") or x.get("description") or "")
        synth = ["candidate_readme"] if hard else []
        dl = x.get("weekly_downloads")
        if dl is None: dl = rng.randint(2000, 400000); synth = synth + ["weekly_downloads"]
        items.append(_item(x["name"], x["target"], False, readme, _publisher_real(x), dl,
                           {"source": "npm" if x["ecosystem"] == "npm" else "pypi", "ecosystem": x["ecosystem"], "relation": x["relation"], "hard": hard,
                            "readme_style": "copied" if hard else "real", "synthetic_fields": synth, "src": x.get("src")}))

    # ---- hardcoded known cases from the pilot (skip any already present)
    have = {it.id for it in items}
    for c, t, squat, eco in _HARDCODED:
        if f"{c}->{t}" in have: continue
        desc = tdesc.get(t.lower()) or _DEFAULT_DESC; inst = "npm i" if eco == "npm" else "pip install"
        if squat:
            items.append(_item(c, t, True, _README["copied"].format(C=c, T=t, D=desc, I=inst), _publisher_fresh(rng), rng.randint(5, 300),
                               {"source": "hardcoded", "ecosystem": eco, "relation": relation(c, t) or "edit1", "hard": False, "readme_style": "copied",
                                "synthetic_fields": ["candidate_readme", "publisher", "weekly_downloads"]}))
        else:
            real = next((x for x in neg_pool if x["name"].lower() == c.lower()), None)
            if real:
                items.append(_item(c, t, False, real.get("readme") or real.get("description", ""), _publisher_real(real), real.get("weekly_downloads") or rng.randint(20000, 5_000_000),
                                   {"source": "hardcoded", "ecosystem": eco, "relation": relation(c, t) or "affix", "hard": False, "readme_style": "real", "synthetic_fields": []}))
            else:
                items.append(_item(c, t, False, f"{c} is an extension/companion for {t}. It adds a focused feature set on top of {t}, is maintained separately, and lists {t} as a peer dependency.",
                                   f"{t.split('.')[0]}-team (account 8 years old, 40+ packages, verified org, repository github.com/{t.split('.')[0]}/{_bare(c)}, {rng.randint(2000, 60000)} stars)",
                                   rng.randint(20000, 5_000_000), {"source": "hardcoded", "ecosystem": eco, "relation": relation(c, t) or "affix", "hard": False, "readme_style": "synthetic",
                                                                 "synthetic_fields": ["candidate_readme", "publisher", "weekly_downloads"]}))
    rng.shuffle(items)
    return items

if __name__ == "__main__":
    import sys
    from collections import Counter
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1200
    items = build(n, seed=0)
    p = write_items(NAME, items)
    print(p, len(items))
    print("by label:", Counter(i.label for i in items))
    print("by source/label:", Counter((i.meta["source"], i.label) for i in items))
    print("by relation/label:", Counter((i.meta["relation"], i.label) for i in items))
    print("by ecosystem/label:", Counter((i.meta["ecosystem"], i.label) for i in items))
    print("hard:", Counter((i.meta["hard"], i.label) for i in items))
    for lbl in (True, False):
        for i in [x for x in items if x.label == lbl][:3]: print(" ", i.id, i.label, i.meta["relation"], "|", i.state["candidate_readme"][:80])
