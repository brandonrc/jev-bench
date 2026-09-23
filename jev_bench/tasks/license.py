"""Task `license`: classify a free-text LICENSE blob into a license family.

Source: ScanCode LicenseDB (https://scancode-licensedb.aboutcode.org), ~2.7k licenses with a
curated `category`. Texts are downloaded once and cached under data/license/texts/.
Each source license yields up to three variants, as in the pilot:
  verbatim   - the text as published
  rebranded  - copyright holder and the license's own name replaced, generic agreement header added
  truncated  - first 1500 chars (only when the text is longer than that)
Plus ~30 inline non-license documents labelled other_unknown.
"""
import json, os, random, re, sys, time
from concurrent.futures import ThreadPoolExecutor

from . import Item, cache_path, write_items

NAME = "license"
QKEY = "family"
CRITERIA = {
    "permissive": "MIT/BSD/Apache/ISC style: use, modify, redistribute freely, keep the notice; no obligation to share source",
    "weak_copyleft": "LGPL/MPL/EPL/CDDL style: modified files or the library itself must stay open, but linking/combining with proprietary code is allowed",
    "strong_copyleft": "GPL style: any distributed derivative work must be released under the same license with full source",
    "network_copyleft": "AGPL/SSPL/EUPL style: copyleft that also triggers when the software is offered over a network as a service",
    "public_domain": "Unlicense/CC0/WTFPL style: all rights waived, no conditions at all",
    "source_available": "BUSL/Elastic style: source is visible but production or competing use is restricted, often converting to open source after a date",
    "noncommercial": "commercial use is prohibited or requires a separate license",
    "other_unknown": "not a software license, or cannot be determined from the text",
}
QUESTION = {QKEY: {
    "type": "choice",
    "instructions": "Which license family does this LICENSE text belong to? Judge by the obligations it imposes, not by its name.",
    "criteria": CRITERIA,
}}
FAMILIES = list(CRITERIA)

BASE_URL = "https://scancode-licensedb.aboutcode.org/"
CAP_PER_FAMILY = 40        # sources per family; x3 variants keeps the total in the 600-900 range
MIN_CHARS = 200
TRUNC_CHARS = 1500

CATEGORY_TO_FAMILY = {
    "Permissive": "permissive",
    "Copyleft": "strong_copyleft",
    "Copyleft Limited": "weak_copyleft",
    "Public Domain": "public_domain",
    "Source-available": "source_available",
    "Non-Commercial": "noncommercial",
    "Proprietary Free": "other_unknown",
    "Commercial": "other_unknown",
    "Free Restricted": "other_unknown",
    "Patent License": "other_unknown",
    "CLA": "other_unknown",
    "Unstated License": "other_unknown",
}
# Explicit overrides win over category and heuristics.
OVERRIDES = {
    "agpl-1.0": "network_copyleft", "agpl-1.0-plus": "network_copyleft", "agpl-2.0": "network_copyleft",
    "agpl-3.0": "network_copyleft", "agpl-3.0-plus": "network_copyleft", "agpl-3.0-linking-exception": "network_copyleft",
    "sspl-1.0": "network_copyleft", "eupl-1.0": "network_copyleft", "eupl-1.1": "network_copyleft", "eupl-1.2": "network_copyleft",
    "ossl-1.0": "network_copyleft", "cpal-1.0": "network_copyleft", "osl-1.0": "network_copyleft", "osl-2.0": "network_copyleft",
    "osl-2.1": "network_copyleft", "osl-3.0": "network_copyleft", "nposl-3.0": "network_copyleft", "rpl-1.1": "network_copyleft",
    "rpl-1.5": "network_copyleft", "watcom-1.0": "network_copyleft", "apple-apsl-2.0": "network_copyleft", "apsl-2.0": "network_copyleft",
    "honest-public-license-1.1": "network_copyleft", "ms-rl": "weak_copyleft",
    "sleepycat": "strong_copyleft", "gpl-2.0": "strong_copyleft", "gpl-3.0": "strong_copyleft",
    "lgpl-2.1": "weak_copyleft", "lgpl-3.0": "weak_copyleft", "mpl-2.0": "weak_copyleft", "epl-2.0": "weak_copyleft", "cddl-1.0": "weak_copyleft",
    "unlicense": "public_domain", "cc0-1.0": "public_domain", "wtfpl-2.0": "public_domain",
    "bsl-1.1": "source_available", "elastic-license-v2": "source_available", "elastic-license-2018": "source_available",
    "cc-by-nc-4.0": "noncommercial", "cc-by-nc-sa-4.0": "noncommercial", "cc-by-nc-nd-4.0": "noncommercial",
}
NETWORK_KEY_RE = re.compile(r"^(agpl|sspl|eupl|ossl|cpal|osl-|nposl|rpl-|tgppl)", re.I)
NETWORK_TEXT_RE = re.compile(
    r"remote network interaction|interact(ing|s)? with it remotely through a computer network|"
    r"network use is distribution|external deployment|deploy(ed|ment).{0,80}network|"
    r"offer(ing)? the (program|software|licensed work|functionality)[^.]{0,80}(as a service|over a network|through a network)",
    re.I | re.S)
NC_KEY_RE = re.compile(r"(^|-)nc(-|$)|non-?commercial", re.I)
NC_TEXT_RE = re.compile(r"non-?commercial (purposes|use)|not (be used|use .{0,40}) for commercial|commercial use .{0,40}(prohibited|not permitted|requires)", re.I)

# --- rebranding, same shape as the pilot ------------------------------------------------------
LICENSE_NAME_RE = re.compile(
    r"(?i)\b(the )?(MIT|Apache|GNU|BSD|Mozilla|Eclipse|Business Source|Elastic|Creative Commons|Server Side Public|"
    r"European Union Public|Open Software|Common Public Attribution|Common Development and Distribution|Boost Software|"
    r"Artistic|Academic Free|Microsoft (Public|Reciprocal)|Sun Public|IBM Public|Python Software Foundation|zlib|ISC|"
    r"SIL Open Font|Educational Community|Sleepycat|Reciprocal Public|Universal Permissive|Q Public|PostgreSQL)"
    r"( General| Lesser| Affero| Library)?( Public)? Licen[cs]e\b")
COPYRIGHT_RE = re.compile(r"(?im)^(\s*)(copyright|\(c\)|©)[^\n]*$")

def _rebrand(text: str) -> str:
    t = COPYRIGHT_RE.sub(r"\1Copyright (c) 2024 Northwind Traders Pty Ltd", text)
    t = LICENSE_NAME_RE.sub("the Northwind Software License", t)
    t = re.sub(r"(?i)\b(GPL|LGPL|AGPL|MPL|EPL|CDDL|BSD|MIT|SSPL|EUPL|BUSL)\b(-|\s)?v?\d(\.\d)?", "NSL-3", t)
    return "NORTHWIND SOFTWARE LICENSE AGREEMENT v3\n\nThis agreement governs use of the Northwind Toolkit.\n\n" + t

# --- inline non-license documents (other_unknown) --------------------------------------------
NEGATIVES = {
    "readme-cli": "# fastq-tools\n\nCommand-line utilities for FASTQ files.\n\n## Install\n\n    pip install fastq-tools\n\n## Usage\n\n    fastq-stats reads.fq.gz\n\nRuns on Python 3.9+. Contributions welcome, see CONTRIBUTING.md.",
    "readme-lib": "## quicksort-rs\n\nA small, allocation-free quicksort for slices. Benchmarks against std::sort are in `bench/`.\n\n```rust\nuse quicksort_rs::sort;\nsort(&mut v);\n```\n\nMSRV is 1.70. CI runs on Linux, macOS and Windows.",
    "readme-badges": "[![CI](https://ci.example/badge.svg)](https://ci.example) [![npm](https://img.shields.io/npm/v/tinyq.svg)](https://npm.im/tinyq)\n\n# tinyq\n\nA 400-byte promise queue with concurrency limits.\n\nSee the docs folder for the API. Questions go in Discussions, bugs in Issues.",
    "contributing": "# Contributing\n\nThanks for your interest! Please open an issue before large changes.\n\n1. Fork the repo and create a branch from `main`.\n2. Run `make test` and make sure everything passes.\n3. Follow the existing code style; we use black and isort.\n4. Sign your commits with `git commit -s`.\n\nBy contributing you agree that your contributions will be licensed under the project's existing license.",
    "cla": "Individual Contributor License Agreement\n\nThank you for your interest in contributing to the Northwind open source projects. In order to clarify the intellectual property license granted with Contributions from any person or entity, Northwind must have a Contributor License Agreement on file that has been signed by each Contributor.\n\n1. Definitions. \"You\" means the individual who submits a Contribution.\n2. Grant of Copyright License. You hereby grant to Northwind and to recipients of software distributed by Northwind a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable copyright license to reproduce, prepare derivative works of, publicly display, sublicense, and distribute Your Contributions.\n3. You represent that you are legally entitled to grant the above license.",
    "privacy": "Privacy Policy\n\nLast updated: March 2024\n\nWe collect crash reports and anonymous usage statistics when telemetry is enabled. Telemetry is off by default. Data is stored for 90 days in the EU and is never sold to third parties. You can request deletion by emailing privacy@example.com.\n\nWe use cookies on the documentation site for session management only.",
    "coc": "# Code of Conduct\n\nWe are committed to providing a friendly, safe and welcoming environment for all, regardless of level of experience, gender identity, disability, ethnicity, religion, or similar personal characteristic.\n\nExamples of unacceptable behavior include harassment, trolling, insulting comments, and publishing others' private information. Instances of abusive behavior may be reported to the maintainers at conduct@example.com. All complaints will be reviewed and investigated.",
    "todo": "TODO: add license\n",
    "placeholder": "LICENSE\n\n(license text to be determined - ask legal before publishing)\n",
    "empty-ish": "See LICENSE.md in the parent directory.\n",
    "changelog": "# Changelog\n\n## 2.3.0 - 2024-05-01\n- Added `--json` output\n- Fixed a crash on empty input\n\n## 2.2.1 - 2024-02-11\n- Bumped dependencies\n- Docs typo fixes\n\n## 2.2.0 - 2023-12-20\n- New `retry` option",
    "security": "# Security Policy\n\n## Supported Versions\n\n| Version | Supported |\n|---|---|\n| 3.x | yes |\n| 2.x | no |\n\n## Reporting a Vulnerability\n\nPlease email security@example.com with a description and reproduction steps. We aim to respond within 72 hours and will credit reporters in the release notes unless you prefer otherwise.",
    "authors": "AUTHORS\n\nThis project is maintained by:\n\n  Alice Rivera <alice@example.com>\n  Bo Tanaka <bo@example.com>\n\nWith contributions from many others, see `git shortlog -sn`.",
    "notice-trademark": "TRADEMARK NOTICE\n\n\"Northwind\" and the Northwind logo are trademarks of Northwind Traders Pty Ltd. Use of the marks in a way that suggests endorsement or affiliation requires prior written permission. Nominative use to refer to the software is permitted.",
    "third-party-index": "THIRD-PARTY NOTICES\n\nThis product bundles the following components. Each is subject to its own license, reproduced in the licenses/ directory:\n\n- zlib 1.3 (licenses/zlib.txt)\n- libpng 1.6.40 (licenses/libpng.txt)\n- Roboto font (licenses/roboto.txt)\n- expat 2.5 (licenses/expat.txt)",
    "install": "INSTALL\n\nBasic installation:\n\n  ./configure\n  make\n  sudo make install\n\nConfiguration options are listed with `./configure --help`. Building the docs requires Sphinx. On Windows use the CMake project under `win/`.",
    "eula-ref": "By downloading this installer you confirm that you have read the terms presented in the setup wizard. The full terms are shown on the second page of the installer and can be printed from there.",
    "issue-template": "---\nname: Bug report\nabout: Create a report to help us improve\n---\n\n**Describe the bug**\nA clear and concise description of what the bug is.\n\n**To Reproduce**\nSteps to reproduce the behavior.\n\n**Expected behavior**\n\n**Environment**\n- OS:\n- Version:",
    "funding": "# Funding\n\nThis project is funded through GitHub Sponsors and Open Collective. Sponsors at the Gold tier get their logo in the README and priority issue triage. Funds pay for CI minutes and occasional contributor bounties.",
    "roadmap": "# Roadmap\n\n## Q3\n- Streaming parser\n- Windows ARM builds\n\n## Q4\n- Plugin API stabilisation\n- 1.0 release\n\nItems are not commitments; priorities shift with contributor availability.",
    "citation": "cff-version: 1.2.0\nmessage: If you use this software, please cite it as below.\nauthors:\n  - family-names: Rivera\n    given-names: Alice\ntitle: fastq-tools\nversion: 2.3.0\ndate-released: 2024-05-01\nurl: https://github.com/example/fastq-tools",
    "dco": "Developer Certificate of Origin\nVersion 1.1\n\nBy making a contribution to this project, I certify that:\n\n(a) The contribution was created in whole or in part by me and I have the right to submit it under the open source license indicated in the file; or\n(b) The contribution is based upon previous work that, to the best of my knowledge, is covered under an appropriate open source license and I have the right under that license to submit that work with modifications.",
    "support": "# Support\n\nCommunity support is available on the Discord server and in GitHub Discussions. Commercial support contracts with SLAs are available from the maintainers' consultancy; email support@example.com for a quote.",
    "maintainers": "MAINTAINERS\n\ncore:\n  - @arivera (release manager)\n  - @btanaka (CI, packaging)\ndocs:\n  - @cchen\n\nDecisions are made by lazy consensus on the mailing list; a maintainer may veto with a stated reason.",
    "notice-apache-style-only": "NOTICE\n\nNorthwind Toolkit\nCopyright 2019-2024 Northwind Traders Pty Ltd\n\nThis product includes software developed at Northwind Traders (https://northwind.example).\nPortions of this software were developed with funding from the Northwind Research Grant.",
    "readme-archived": "# legacy-parser (ARCHIVED)\n\nThis repository is no longer maintained. Use `new-parser` instead. Issues and pull requests are closed. The code remains available for reference.",
    "gitignore": "# Byte-compiled / optimized\n__pycache__/\n*.py[cod]\n\n# Environments\n.env\n.venv/\n\n# Build\nbuild/\ndist/\n*.egg-info/",
    "release-notes": "Release 4.1.0\n\nHighlights:\n* 30% faster cold start\n* New `--profile` flag\n* Deprecated `legacy_mode`; it will be removed in 5.0\n\nUpgrade notes: run `tool migrate` once after upgrading.",
    "readme-docker": "# northwind/api\n\nDocker image for the Northwind API.\n\n    docker run -p 8080:8080 northwind/api:latest\n\nEnvironment variables:\n- `DATABASE_URL`\n- `LOG_LEVEL` (default `info`)\n\nTags follow semver; `latest` tracks the newest stable release.",
    "export-notice": "EXPORT CONTROL NOTICE\n\nThis distribution includes cryptographic software. The country in which you currently reside may have restrictions on the import, possession, use, and/or re-export of encryption software. Before using this software, please check your country's laws and regulations.",
}

# --- data access --------------------------------------------------------------------------------
def _http():
    import httpx
    return httpx.Client(base_url=BASE_URL, timeout=30, headers={"User-Agent": "jev-bench/0.1 (+https://github.com/brandonrc/jev-bench)"})

def _get_with_retry(client, path, tries=4):
    for i in range(tries):
        try:
            r = client.get(path)
            if r.status_code == 200:
                return r.text
            if r.status_code == 404:
                return None
        except Exception:
            pass
        time.sleep(1.5 * (i + 1))
    return None

def load_index() -> list[dict]:
    p = cache_path(NAME, "index.json")
    if not os.path.exists(p):
        with _http() as c:
            open(p, "w").write(_get_with_retry(c, "index.json") or "[]")
    return json.load(open(p))

def fetch_texts(keys: list[str]) -> dict[str, str]:
    """Return {key: text} for keys, downloading missing ones (<=8 concurrent) into data/license/texts/."""
    tdir = cache_path(NAME, "texts"); os.makedirs(tdir, exist_ok=True)
    out, missing = {}, []
    for k in keys:
        fp = os.path.join(tdir, f"{k}.LICENSE")
        if os.path.exists(fp):
            out[k] = open(fp, encoding="utf-8", errors="replace").read()
        else:
            missing.append(k)
    if missing:
        with _http() as c, ThreadPoolExecutor(max_workers=8) as ex:
            def job(k):
                t = _get_with_retry(c, f"{k}.LICENSE")
                open(os.path.join(tdir, f"{k}.LICENSE"), "w", encoding="utf-8").write(t if t is not None else "")
                return k, t or ""
            for k, t in ex.map(job, missing):
                out[k] = t
    return out

def family_for(entry: dict, text: str) -> str:
    key = entry["license_key"]
    if key in OVERRIDES:
        return OVERRIDES[key]
    cat = entry.get("category")
    fam = CATEGORY_TO_FAMILY.get(cat, "other_unknown")
    if fam == "strong_copyleft" and (NETWORK_KEY_RE.search(key) or NETWORK_TEXT_RE.search(text)):
        return "network_copyleft"
    if fam == "other_unknown" and cat in ("Proprietary Free", "Commercial", "Free Restricted") and (NC_KEY_RE.search(key) or NC_TEXT_RE.search(text)):
        return "noncommercial"
    return fam

# --- build --------------------------------------------------------------------------------------
def build(n: int = 0, seed: int = 7) -> list[Item]:
    rng = random.Random(seed)
    index = [e for e in load_index() if not e.get("is_exception") and not e.get("is_deprecated") and e.get("category") in CATEGORY_TO_FAMILY]
    index.sort(key=lambda e: e["license_key"])

    # Provisional family from category/key only (no text yet) so we only download what we might use.
    def provisional(e):
        k = e["license_key"]
        if k in OVERRIDES: return OVERRIDES[k]
        fam = CATEGORY_TO_FAMILY[e["category"]]
        if fam == "strong_copyleft" and NETWORK_KEY_RE.search(k): return "network_copyleft"
        if fam == "other_unknown" and NC_KEY_RE.search(k): return "noncommercial"
        return fam
    buckets: dict[str, list[dict]] = {f: [] for f in FAMILIES}
    for e in index:
        buckets[provisional(e)].append(e)
    # Copyleft texts are all needed to run the network-language heuristic; other families get a slack sample.
    wanted = []
    for fam, entries in buckets.items():
        rng.shuffle(entries)
        take = len(entries) if fam in ("strong_copyleft", "network_copyleft") else min(len(entries), int(CAP_PER_FAMILY * 2.5))
        wanted.extend(entries[:take])
    texts = fetch_texts([e["license_key"] for e in wanted])

    # Final family with text heuristics; drop short/missing texts.
    final: dict[str, list[tuple[dict, str]]] = {f: [] for f in FAMILIES}
    for e in wanted:
        t = texts.get(e["license_key"], "").strip()
        if len(t) < MIN_CHARS:
            continue
        final[family_for(e, t)].append((e, t))

    items: list[Item] = []
    for fam in FAMILIES:
        srcs = sorted(final[fam], key=lambda et: et[0]["license_key"])
        rng.shuffle(srcs)
        cap = CAP_PER_FAMILY - (len(NEGATIVES) // 3 if fam == "other_unknown" else 0)
        for e, t in srcs[:max(cap, 0)]:
            k = e["license_key"]
            variants = [("verbatim", t), ("rebranded", _rebrand(t))]
            if len(t) > TRUNC_CHARS:
                variants.append(("truncated", t[:TRUNC_CHARS]))
            for vname, vt in variants:
                items.append(Item(task=NAME, id=f"{k}/{vname}", state={"license_text": vt}, label=fam,
                                  meta={"variant": vname, "scancode_key": k, "category": e.get("category"),
                                        "spdx": e.get("spdx_license_key"), "chars": len(vt), "approx_tokens": len(vt) // 4}))
    for nid, text in NEGATIVES.items():
        items.append(Item(task=NAME, id=f"neg-{nid}/verbatim", state={"license_text": text}, label="other_unknown",
                          meta={"variant": "verbatim", "scancode_key": None, "category": "inline-negative",
                                "spdx": None, "chars": len(text), "approx_tokens": len(text) // 4}))
    rng.shuffle(items)
    return items[:n] if n and n > 0 else items

if __name__ == "__main__":
    import collections
    items = build(0, int(sys.argv[1]) if len(sys.argv) > 1 else 7)
    print("total items:", len(items))
    for fam, cnt in sorted(collections.Counter(i.label for i in items).items()):
        print(f"  {fam:18s} {cnt}")
    print("variants:", dict(collections.Counter(i.meta["variant"] for i in items)))
    print("wrote", write_items(NAME, items))


# --- lenient scoring -------------------------------------------------------
# ScanCode's categories and our rubric disagree on a few boundaries; these pairs are treated as
# equivalent under the "lenient" metric that analyze.py reports next to strict accuracy.
LENIENT_PAIRS = {
    frozenset({"noncommercial", "source_available"}),   # RSALv2, CockroachDB, FSL: ScanCode says Non-Commercial
    frozenset({"other_unknown", "permissive"}),         # ScanCode "Proprietary Free" holds plain permissive notices
    frozenset({"strong_copyleft", "network_copyleft"}), # AGPL-like clauses inside otherwise-GPL texts
}
def equivalent(label, pred) -> bool:
    return label == pred or frozenset({label, pred}) in LENIENT_PAIRS
