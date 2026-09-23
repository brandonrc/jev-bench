"""Laya smoke test: load on cuda:0, run a typosquat noul + curation choice, time it."""
import time, json, statistics, sys
import laya

CKPT = sys.argv[1] if len(sys.argv) > 1 else "typed-decisions"
t0 = time.perf_counter()
agent = laya.load("convaiinnovations/laya", subfolder=(None if CKPT=="base" else CKPT), device="cuda:0")
print(f"load[{CKPT}]: {time.perf_counter()-t0:.1f}s")

state = {
    "candidate": "lodahs",
    "target": "lodash",
    "publisher": "npm-user-93321 (account age 3 days, 1 package)",
    "downloads_last_week": 41,
    "readme": "Lodash modular utilities. A modern JavaScript utility library delivering modularity, performance & extras. Install: npm i lodahs",
    "license": "MIT",
    "install_script": "postinstall: node ./setup.js (fetches remote payload from http://185.x.x.x/a.sh)",
}
questions = {
    "impersonation": {
        "type": "noul",
        "instructions": "Is this package a deliberate impersonation of the target package, given its README, publisher and name?",
        "criteria": {"true": "copies the target's README/name and hides its origin", "false": "an honest fork, plugin, or unrelated package"},
    },
    "verdict": {
        "type": "choice",
        "instructions": "Classify this package for curation review.",
        "criteria": {
            "malicious": "install scripts fetch remote code, credential theft, obfuscation",
            "abandoned": "no releases for years, broken deps, unmaintained",
            "license_incompatible": "license conflicts with an allowlist of permissive licenses",
            "benign": "normal, maintained, honest package",
        },
    },
}

# warmup
for _ in range(3):
    agent.predict(state, questions)

lat = []
for _ in range(50):
    t = time.perf_counter(); r = agent.predict(state, questions); lat.append((time.perf_counter()-t)*1000)
lat.sort()
print(f"single (2 q): p50={statistics.median(lat):.1f}ms p95={lat[int(len(lat)*0.95)-1]:.1f}ms min={lat[0]:.1f}ms")
print(json.dumps(r["answers"] if isinstance(r, dict) else r, indent=1, default=str)[:800])

states = [dict(state, candidate=f"lodahs{i}") for i in range(256)]
t = time.perf_counter(); rb = agent.predict_batch(states, questions, batch_size=64); dt = time.perf_counter()-t
print(f"batch 256 states x 2 q: {dt*1000:.0f}ms total, {dt*1000/256:.2f}ms/state")
