"""Charts for the engineering-blog post, from results/fair. Palette: validated categorical slots (dataviz reference)."""
import json, sys, os
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
OUT = sys.argv[1] if len(sys.argv) > 1 else "docs/charts"; os.makedirs(OUT, exist_ok=True)
S = json.load(open("results/fair/summary.json")); get = lambda t, e: next((s for s in S if s["task"] == t and s["engine"] == e), None)
TASKS = [("quarantine", "Quarantine reason"), ("curation", "Curation review"), ("reachability", "Finding reachability"), ("license", "License family")]
ENG = [("jev", "Jev (hosted)", "#2a78d6"), ("claude-haiku-4-5", "Claude Haiku 4.5 (hosted)", "#eda100"), ("laya-typed-decisions", "Laya, off the shelf", "#1baf7a"), ("laya-ft", "Laya, fine-tuned", "#eb6834"), ("clm-ft", "CLM-8B, fine-tuned head", "#e87ba4")]
INK, INK2, GRID = "#141514", "#4e514d", "#ebece8"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK})

# 1. accuracy by task, grouped horizontal bars (typosquat excluded: leaky for the fine-tunes)
fig, ax = plt.subplots(figsize=(9, 5.8), dpi=160); n = len(ENG); h = 0.15
for ti, (tk, tn) in enumerate(TASKS):
    for ei, (ek, en, c) in enumerate(ENG):
        s = get(tk, ek); v = s["acc"] * 100 if s else 0
        y = ti + (ei - (n - 1) / 2) * h
        ax.barh(y, v, height=h * 0.92, color=c, label=en if ti == 0 else None)
        ax.text(v + 0.8, y, f"{v:.0f}%", va="center", fontsize=8.5, color=INK, family="DejaVu Sans Mono")
ax.set_yticks(range(len(TASKS))); ax.set_yticklabels([t[1] for t in TASKS]); ax.invert_yaxis()
ax.set_xlim(0, 108); ax.set_xticks([0, 25, 50, 75, 100]); ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"])
ax.xaxis.grid(True, color=GRID); ax.set_axisbelow(True)
for sp in ("top", "right", "left"): ax.spines[sp].set_visible(False)
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=3, frameon=False, fontsize=8.5); ax.set_title("Accuracy on held-out test splits, 768-token capped inputs", loc="left", fontsize=11, color=INK)
fig.tight_layout(); fig.savefig(f"{OUT}/accuracy-by-task.png"); plt.close(fig)

# 2. latency, single stream cold, median across tasks (log-free, linear)
lat = {}
for l in open("results/fair/latency.jsonl"):
    r = json.loads(l); e = {"laya-ft-fair-laya-s3": "laya-ft"}.get(r["engine"], r["engine"]); lat.setdefault(e, {})[r["task"]] = r["p50_ms"]
fig, ax = plt.subplots(figsize=(9, 3.4), dpi=160)
rows = [(en, sorted(lat[ek].values())[len(lat[ek]) // 2], c) for ek, en, c in ENG if ek in lat]
for i, (en, v, c) in enumerate(rows):
    ax.barh(i, v, height=0.6, color=c); ax.text(v + 12, i, f"{v:.0f} ms", va="center", fontsize=9, color=INK, family="DejaVu Sans Mono")
ax.set_yticks(range(len(rows))); ax.set_yticklabels([r[0] for r in rows]); ax.invert_yaxis(); ax.set_xlim(0, 1350)
ax.xaxis.grid(True, color=GRID); ax.set_axisbelow(True); ax.set_xlabel("median p50 per decision, one request at a time, cold cache")
for sp in ("top", "right", "left"): ax.spines[sp].set_visible(False)
ax.set_title("Latency per decision", loc="left", fontsize=11, color=INK); fig.tight_layout(); fig.savefig(f"{OUT}/latency.png"); plt.close(fig)

# 3. context sweep: Laya retrained per cap, license + reachability
import glob
caps = [256, 512, 768, 1536, 2048]; series = {"reachability": [], "license": []}
for cap in caps:
    for t in series:
        f = f"results/fair/context/laya-{cap}/laya-ft-ctx-laya-{cap}__{t}.jsonl"
        rs = [json.loads(l) for l in open(f)]; series[t].append(100 * sum(r["pred"] == r["label"] for r in rs) / len(rs))
fig, ax = plt.subplots(figsize=(9, 3.6), dpi=160)
for (t, c) in (("reachability", "#2a78d6"), ("license", "#eb6834")):
    ax.plot(caps, series[t], color=c, linewidth=2, marker="o", markersize=6, markeredgecolor="white", markeredgewidth=1.5, label={"reachability": "Finding reachability", "license": "License family"}[t])
    ax.text(caps[-1] + 40, series[t][-1], f"{series[t][-1]:.0f}%", va="center", fontsize=9, color=INK, family="DejaVu Sans Mono")
ax.set_xticks(caps); ax.set_xticklabels([f"{c:,}" for c in caps]); ax.set_xlim(150, 2300); ax.set_ylim(50, 100)
ax.set_yticks([50, 60, 70, 80, 90, 100]); ax.set_yticklabels([f"{v}%" for v in ax.get_yticks()]); ax.yaxis.grid(True, color=GRID); ax.set_axisbelow(True)
ax.set_xlabel("state cap, tokens (Laya retrained at each cap)"); ax.legend(frameon=False, loc="lower right", fontsize=9)
for sp in ("top", "right"): ax.spines[sp].set_visible(False)
ax.set_title("How much context the task needs", loc="left", fontsize=11, color=INK); fig.tight_layout(); fig.savefig(f"{OUT}/context-sweep.png"); plt.close(fig)
print("charts written to", OUT)
