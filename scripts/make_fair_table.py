"""Headline table for the write-up from results/fair/: accuracy per column (mean ± sd over seeds) and the
LATEST cold single-stream latency record per engine/task. Writes docs/_fair_table.md."""
import json
S = json.load(open("results/fair/summary.json"))
get = lambda t, e: next((s for s in S if s["task"] == t and s["engine"] == e), None)
tasks = ["quarantine", "curation", "typosquat", "reachability", "license"]
names = {"quarantine": "Quarantine reason", "curation": "Curation review", "typosquat": "Typosquat 2nd stage", "reachability": "Finding reachability", "license": "License family"}
cols = [("jev", "Jev"), ("claude-haiku-4-5", "Haiku 4.5"), ("laya-typed-decisions", "Laya (off the shelf)"), ("laya-ft", "Laya tuned ×3"), ("clm-8b", "CLM-8B"), ("clm-ft", "CLM tuned ×3")]
alias = {"laya-ft-fair-laya-s3": "laya-ft"}
L = ["| Task | " + " | ".join(c[1] for c in cols) + " |", "|---|" + "---|" * len(cols)]
for t in tasks:
    row = []
    for k, _ in cols:
        s = get(t, k)
        if not s: row.append("–"); continue
        v = f"{s['acc']*100:.0f}%" + (f" ±{s['acc_sd']*100:.1f}" if s.get("acc_sd") is not None else "")
        if t == "typosquat" and k in ("laya-ft", "clm-ft"): v += " (leaky)"
        row.append(v)
    L.append(f"| {names[t]} | " + " | ".join(row) + " |")
lat = {}
for l in open("results/fair/latency.jsonl"):
    r = json.loads(l); e = alias.get(r["engine"], r["engine"]); lat.setdefault(e, {})[r["task"]] = r["p50_ms"]   # later records overwrite earlier ones
def med(e):
    v = sorted(x for x in lat.get(e, {}).values() if x); return f"{v[len(v)//2]:.0f} ms" if v else "–"
L.append("| Latency p50, single stream, cold | " + " | ".join(med(k) for k, _ in cols) + " |")
open("docs/_fair_table.md", "w").write("\n".join(L) + "\n"); print("\n".join(L))
