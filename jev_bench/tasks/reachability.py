"""Task: reachability (noul).

"Is this scanner finding reachable in the declared dependency graph?" -- the sort-not-suppress
triage of Trivy/Grype noise. Real npm advisories from OSV, synthetic but realistic resolved
dependency trees built from real npm package names. Ground truth is computed by walking the
graph in code; nothing is hand-labelled.

Reachable := the affected package is present in the RESOLVED production dependency graph
(direct or transitive; not dev-only; not an optional dependency that was skipped) at a version
inside the advisory's affected range, reached from the root through a chain of declared deps.
"""
import io, json, os, random, re, zipfile
import httpx
from . import Item, cache_path

NAME = "reachability"
QKEY = "reachable"
RULE = ("A finding is REACHABLE only if ALL of these hold: (1) the exact package named in the finding is present in "
        "the resolved tree (a similarly named package does not count); (2) it is reached from the root through a chain "
        "of production dependencies -- a package that appears only under devDependencies, or only as an optional "
        "dependency marked skipped, is NOT reachable; (3) the version actually resolved in the tree is inside the "
        "advisory's affected_range (introduced <= version < fixed), comparing semver numerically component by component.")
QUESTION = {QKEY: {
    "type": "noul",
    "instructions": "Is this vulnerability scanner finding reachable in the declared dependency graph of the root package? " + RULE,
    "criteria": {"true": "the affected package, at an affected version, sits on a production dependency path from the root",
                 "false": "absent, wrong (fixed) version, lookalike name, dev-only, or optional-skipped"},
}}

OSV_URL = "https://osv-vulnerabilities.storage.googleapis.com/npm/all.zip"

# Real, popular npm names for filler nodes (the anvaka npm-rank URL 404s; advisory package names are added too).
TOP_NPM = """lodash chalk react react-dom express commander debug axios moment uuid fs-extra async tslib request bluebird
yargs glob semver minimist mkdirp colors underscore inquirer body-parser webpack typescript rxjs babel-core dotenv
classnames prop-types core-js jquery vue redux socket.io ws mocha jest eslint prettier rimraf through2 shelljs
cheerio q ora js-yaml node-fetch path-to-regexp qs cross-spawn execa chokidar readable-stream micromatch
strip-ansi ansi-styles supports-color has-flag escape-string-regexp isarray inherits safe-buffer string_decoder
once wrappy end-of-stream pump graceful-fs object-assign resolve is-glob picomatch braces fill-range to-regex-range
is-number kind-of ms iconv-lite mime mime-types mime-db negotiator accepts depd on-finished ee-first statuses
send serve-static etag fresh range-parser vary cookie cookie-signature finalhandler parseurl encodeurl merge-descriptors
methods array-flatten content-type content-disposition type-is media-typer setprototypeof utils-merge
tar minipass yallist lru-cache ajv fast-deep-equal json-schema-traverse uri-js punycode source-map
convert-source-map ci-info npmlog gauge are-we-there-yet delegates wide-align string-width emoji-regex
is-fullwidth-code-point yaml dayjs date-fns nanoid immer zod joi validator postcss autoprefixer
sass less stylus tailwindcss vite rollup esbuild terser uglify-js acorn espree estraverse esprima
""".split()

_LOOKALIKE = ["@types/{p}", "{p}-cli", "{p}.js", "{p}-utils", "{p}-compat", "eslint-plugin-{p}"]


# ---------- semver ----------
def parse_ver(v):
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?", v.strip())
    if not m:
        raise ValueError(v)
    core = tuple(int(x) for x in m.groups()[:3]); pre = m.group(4)
    # release sorts above any prerelease of the same core: (core, 1) vs (core, 0, pre)
    return (core, 1, ()) if pre is None else (core, 0, tuple(int(p) if p.isdigit() else p for p in pre.split(".")))

def _cmp_key(v):
    core, rel, pre = parse_ver(v)
    return (core, rel, tuple((0, p) if isinstance(p, int) else (1, p) for p in pre))

def ver_lt(a, b): return _cmp_key(a) < _cmp_key(b)
def in_range(v, intro, fixed): return not ver_lt(v, intro) and ver_lt(v, fixed)

def bump(v, patch=1, minor=0):
    (M, m, p), _, _ = parse_ver(v); return f"{M}.{m + minor}.{(p + patch) if not minor else 0}"

def affected_version(intro, fixed, rng):
    """A version inside [intro, fixed). Prefer something strictly between when the range allows it."""
    cands = [intro]
    for step in (1, 2, 3, 5, 10):
        c = bump(intro, patch=step)
        if in_range(c, intro, fixed): cands.append(c)
    c = bump(intro, minor=1)
    if in_range(c, intro, fixed): cands.append(c)
    return rng.choice(cands)

def near_boundary_version(intro, fixed):
    """Largest version we can name below `fixed` (patch - 1), still >= intro; else intro."""
    (M, m, p), _, _ = parse_ver(fixed)
    if p > 0:
        c = f"{M}.{m}.{p - 1}"
        if in_range(c, intro, fixed): return c
    return intro

def clean_ver(v):
    """Reject prerelease/odd version strings so states stay readable."""
    return bool(re.fullmatch(r"\d+\.\d+\.\d+", v))


# ---------- advisories ----------
def load_advisories(limit=150, seed=0):
    p = cache_path(NAME, "advisories.json")
    if os.path.exists(p):
        adv = json.load(open(p))
    else:
        zp = cache_path(NAME, "all.zip")
        if not os.path.exists(zp):
            with httpx.stream("GET", OSV_URL, timeout=600, follow_redirects=True) as r, open(zp, "wb") as f:
                for chunk in r.iter_bytes(): f.write(chunk)
        z = zipfile.ZipFile(zp); adv = []
        for n in sorted(z.namelist()):
            if not n.endswith(".json"): continue
            d = json.loads(z.read(n))
            if d.get("id", "").startswith("MAL-") or any(a.startswith("MAL-") for a in d.get("aliases", [])): continue
            if d.get("withdrawn"): continue
            sev = (d.get("database_specific") or {}).get("severity") or "UNKNOWN"
            for aff in d.get("affected", []):
                if aff.get("package", {}).get("ecosystem") != "npm": continue
                for r in aff.get("ranges", []):
                    if r.get("type") != "SEMVER": continue
                    ev = r.get("events", [])
                    intro = next((e["introduced"] for e in ev if "introduced" in e), None)
                    fixed = next((e["fixed"] for e in ev if "fixed" in e), None)
                    if not intro or not fixed or intro == "0" or not clean_ver(intro) or not clean_ver(fixed): continue
                    if not ver_lt(intro, fixed): continue
                    adv.append({"id": d["id"], "package": aff["package"]["name"], "introduced": intro, "fixed": fixed,
                                "summary": (d.get("summary") or d.get("details") or "")[:160].replace("\n", " "), "severity": sev})
        json.dump(adv, open(p, "w"))
    # one advisory per package, deterministic pick
    rng = random.Random(seed); by_pkg = {}
    for a in adv: by_pkg.setdefault(a["package"], []).append(a)
    pkgs = sorted(by_pkg); rng.shuffle(pkgs)
    return [rng.choice(by_pkg[k]) for k in pkgs[:limit]]


# ---------- graph ----------
class Graph:
    """root -> children; each edge carries a kind in {prod, dev, optional, optional-skipped}."""
    def __init__(self, rng, pool, n_nodes, max_depth):
        self.rng = rng; self.edges = []  # (parent, child, version, kind)
        self.versions = {}
        self.depth = {"root": 0}
        names = rng.sample(pool, n_nodes)
        # direct deps
        n_direct = max(3, n_nodes // 4)
        frontier = []
        for i, nm in enumerate(names[:n_direct]):
            kind = "prod" if i < n_direct * 0.6 else ("dev" if i < n_direct * 0.9 else "optional")
            self._add("root", nm, kind); frontier.append(nm)
        for nm in names[n_direct:]:
            parent = rng.choice([f for f in frontier if self.depth[f] < max_depth] or ["root"])
            self._add(parent, nm, "prod" if parent != "root" else "prod"); frontier.append(nm)
        self.pool_left = [p for p in pool if p not in self.versions]

    def _add(self, parent, child, kind, version=None):
        if version is None:
            version = self.versions.get(child) or f"{self.rng.randint(0, 9)}.{self.rng.randint(0, 20)}.{self.rng.randint(0, 30)}"
        self.versions.setdefault(child, version)
        self.edges.append((parent, child, self.versions[child], kind))
        self.depth[child] = min(self.depth.get(child, 99), self.depth[parent] + 1)

    def plant(self, pkg, version, kind, depth_min=1, depth_max=99, parent=None):
        if parent is None:
            cands = [n for n, d in self.depth.items() if depth_min <= d <= depth_max and n != "root"
                     and self.kind_of(n) == ("prod" if kind == "prod" else kind)]
            parent = self.rng.choice(cands) if cands else "root"
        self.versions[pkg] = version
        self._add(parent, pkg, kind if parent == "root" else "prod")
        return parent

    def kind_of(self, node):
        """Kind of the top-level edge on the path to node (prod/dev/optional)."""
        for p, c, v, k in self.edges:
            if c == node:
                return k if p == "root" else self.kind_of(p)
        return None

    def package_json(self):
        pj = {"name": "@acme/app", "version": "2.4.0", "dependencies": {}, "devDependencies": {}, "optionalDependencies": {}}
        for p, c, v, k in self.edges:
            if p == "root":
                key = {"prod": "dependencies", "dev": "devDependencies"}.get(k, "optionalDependencies")
                pj[key][c] = "^" + v
        return {k: v for k, v in pj.items() if v or k in ("name", "version")}

    def resolved_lines(self):
        out = []
        for p, c, v, k in self.edges:
            tag = k if p == "root" else self._top_kind(c)
            out.append(f"{p} -> {c}@{v} [{tag}]")
        return out

    def _top_kind(self, node):
        k = self.kind_of(node); return k

    # ---- ground truth: walk from root over production, non-skipped edges ----
    def reachable(self, pkg, intro, fixed):
        seen, stack = set(), ["root"]
        while stack:
            n = stack.pop()
            for p, c, v, k in self.edges:
                if p != n or k in ("dev", "optional-skipped"): continue
                if c == pkg and in_range(v, intro, fixed): return True
                if c not in seen: seen.add(c); stack.append(c)
        return False


SCENARIOS = "abcdefghi"

def build(n=450, seed=0):
    rng = random.Random(seed)
    advisories = load_advisories(150, seed)
    items = []
    for i in range(n):
        adv = advisories[i % len(advisories)]
        sc = SCENARIOS[i % len(SCENARIOS)]
        pkg, intro, fixed = adv["package"], adv["introduced"], adv["fixed"]
        pool = [p for p in TOP_NPM + [a["package"] for a in advisories] if p != pkg and not p.startswith(pkg)]
        pool = sorted(set(pool))
        n_nodes = rng.randint(15, 80); max_depth = rng.randint(1, 5)
        g = Graph(rng, pool, n_nodes, max_depth)
        aff_v = affected_version(intro, fixed, rng)
        reported = aff_v; readme_note = None; planted_depth = None
        if sc == "a":      # prod transitive, affected
            parent = g.plant(pkg, aff_v, "prod", depth_min=1)
        elif sc == "b":    # direct prod, affected
            parent = g.plant(pkg, aff_v, "prod", parent="root")
        elif sc == "c":    # present at fixed (or later) version
            fv = fixed if rng.random() < 0.6 else bump(fixed, patch=rng.randint(1, 4))
            parent = g.plant(pkg, fv, "prod", parent=rng.choice(["root", None])); reported = fv
        elif sc == "d":    # dev-only, affected
            parent = g.plant(pkg, aff_v, "dev", parent="root") if rng.random() < 0.5 else g.plant(pkg, aff_v, "dev")
        elif sc == "e":    # optional, skipped
            parent = g.plant(pkg, aff_v, "optional-skipped", parent="root")
        elif sc == "f":    # lookalike name present, real package absent
            look = rng.choice(_LOOKALIKE).format(p=pkg)
            parent = g.plant(look, aff_v, "prod", parent=rng.choice(["root", None]))
        elif sc == "g":    # absent; scanner matched a vendored-copy string in a README
            parent = None
            readme_note = f"README of {rng.choice(list(g.versions))}: 'includes a vendored, minified copy of {pkg} {aff_v} under lib/vendor/'"
        elif sc == "h":    # two hops, version just below the fixed boundary
            bv = near_boundary_version(intro, fixed); reported = bv
            mid = g.plant(rng.choice(g.pool_left), f"{rng.randint(1,5)}.{rng.randint(0,9)}.{rng.randint(0,9)}", "prod", parent="root")
            parent = g.plant(pkg, bv, "prod", parent=mid)
        elif sc == "i":    # both dev and prod paths, affected
            g.plant(pkg, aff_v, "dev", parent="root")
            parent = g.plant(pkg, aff_v, "prod", depth_min=1)
        if parent is not None and sc != "f":
            planted_depth = g.depth.get(pkg)
        label = g.reachable(pkg, intro, fixed)
        expected = sc in "abhi"
        assert label == expected, (i, sc, label, expected)
        declared = {"package.json": g.package_json(), "resolved_tree": g.resolved_lines()}
        if readme_note: declared["scanner_match_context"] = readme_note
        state = {"finding": {"id": adv["id"], "package": pkg, "affected_range": f">={intro} <{fixed}",
                             "installed_version_reported_by_scanner": reported, "summary": adv["summary"], "severity": adv["severity"]},
                 "declared": declared}
        # keep states bounded (~6k chars): trim filler edges that are not on the planted path
        while len(json.dumps(state)) > 6000 and len(declared["resolved_tree"]) > 12:
            for j, line in enumerate(declared["resolved_tree"]):
                if pkg not in line and (parent is None or f"-> {parent}@" not in line) and "root ->" not in line:
                    declared["resolved_tree"].pop(j); break
            else:
                break
        items.append(Item(NAME, f"reach-{i:04d}-{sc}-{adv['id']}", state, label,
                          {"scenario": sc, "depth": planted_depth, "nodes": len(g.versions), "advisory_id": adv["id"],
                           "severity": adv["severity"], "state_chars": len(json.dumps(state))}))
    return items


# ---------- independent re-check from the rendered state (used by __main__ and tests) ----------
def recheck(item):
    """Re-derive the label purely from the serialized state text, without the Graph object."""
    st = item.state; pkg = st["finding"]["package"]
    m = re.match(r">=(\S+) <(\S+)", st["finding"]["affected_range"]); intro, fixed = m.groups()
    edges = []
    for line in st["declared"]["resolved_tree"]:
        m = re.match(r"(\S+) -> (\S+)@(\S+) \[(\S+)\]", line); p, c, v, k = m.groups(); edges.append((p, c, v, k))
    reach, stack, seen = False, ["root"], set()
    while stack:
        n = stack.pop()
        for p, c, v, k in edges:
            if p != n or k in ("dev", "optional-skipped"): continue
            if c == pkg and in_range(v, intro, fixed): reach = True
            if c not in seen: seen.add(c); stack.append(c)
    return reach


if __name__ == "__main__":
    import collections, sys
    from . import write_items
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 450
    items = build(n, seed=0)
    path = write_items(NAME, items)
    cnt = collections.Counter((it.meta["scenario"], it.label) for it in items)
    print(f"wrote {len(items)} items -> {path}")
    for sc in SCENARIOS:
        print(f"  scenario {sc}: True={cnt[(sc, True)]} False={cnt[(sc, False)]}")
    print("  labels:", collections.Counter(it.label for it in items))
    print("  state chars: max", max(it.meta["state_chars"] for it in items), "mean", sum(it.meta["state_chars"] for it in items) // len(items))
    rng = random.Random(1); sample = rng.sample(items, 5)
    for it in sample:
        assert recheck(it) == it.label, it.id
    print("  independent recheck of 5 random items agrees:", [it.id for it in sample])
    print("  examples:", [it.id for it in items[:3]])
