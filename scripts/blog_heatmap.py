"""Accuracy heatmap for the post: engines x tasks, one sequential hue (light = low, dark = high), numbers printed in
every cell so color never carries the value alone. Second panel: difference vs Jev as a diverging scale with a
neutral midpoint (worse than the hosted baseline / same / better). Brand-leaning palette: OpenTeams-style sky blue
for the sequential ramp; amber vs blue for the diverging pair, gray at zero."""
import json, sys, os
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
OUT = sys.argv[1] if len(sys.argv) > 1 else "docs/charts"; os.makedirs(OUT, exist_ok=True)
S = json.load(open("results/fair/summary.json")); get = lambda t, e: next((s for s in S if s["task"] == t and s["engine"] == e), None)
TASKS = [("quarantine", "Quarantine\nreason"), ("curation", "Curation\nreview"), ("reachability", "Finding\nreachability"), ("license", "License\nfamily")]
ENG = [("jev", "Jev (hosted)"), ("claude-haiku-4-5", "Claude Haiku 4.5 (hosted)"), ("laya-typed-decisions", "Laya, off the shelf"), ("laya-ft", "Laya, fine-tuned"), ("clm-8b", "CLM-8B, off the shelf"), ("clm-ft", "CLM-8B, fine-tuned head")]
INK, INK2, GRID = "#2F2D2E", "#5c5a5b", "#e4e4e4"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2})
acc = [[(get(t, e)["acc"] * 100 if get(t, e) else float("nan")) for t, _ in TASKS] for e, _ in ENG]
jev = [get(t, "jev")["acc"] * 100 for t, _ in TASKS]
diff = [[a - j for a, j in zip(row, jev)] for row in acc]

seq = LinearSegmentedColormap.from_list("ot_blue", ["#f5f9fd", "#cfe6fb", "#72BEFA", "#2a78d6", "#123f7a"])
div = LinearSegmentedColormap.from_list("ot_div", ["#c96f00", "#f1c46b", "#e8e6e3", "#8fc7f5", "#1f5fa8"])  # amber = below Jev, gray = same, blue = above

fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6), dpi=160, gridspec_kw={"width_ratios": [1, 1]})
def panel(ax, M, cmap, norm, title, fmt, ink_rule):
    im = ax.imshow(M, cmap=cmap, norm=norm, aspect="auto")
    ax.set_xticks(range(len(TASKS))); ax.set_xticklabels([t[1] for t in TASKS], fontsize=9)
    ax.set_yticks(range(len(ENG))); ax.set_yticklabels([e[1] for e in ENG], fontsize=9)
    ax.tick_params(length=0); [sp.set_visible(False) for sp in ax.spines.values()]
    ax.set_xticks([x - 0.5 for x in range(1, len(TASKS))], minor=True); ax.set_yticks([y - 0.5 for y in range(1, len(ENG))], minor=True)
    ax.grid(which="minor", color="white", linewidth=2); ax.tick_params(which="minor", length=0)
    for i, row in enumerate(M):
        for j, v in enumerate(row):
            ax.text(j, i, fmt(v), ha="center", va="center", fontsize=9.5, color=ink_rule(v), family="DejaVu Sans Mono")
    ax.set_title(title, loc="left", fontsize=10.5, color=INK, pad=10)
    return im
im1 = panel(axes[0], acc, seq, plt.Normalize(0, 100), "Accuracy on held-out test splits", lambda v: f"{v:.0f}%", lambda v: "white" if v >= 70 else INK)
im2 = panel(axes[1], diff, div, TwoSlopeNorm(vmin=-90, vcenter=0, vmax=20), "Difference from Jev, percentage points", lambda v: ("0" if abs(v) < 0.5 else f"{v:+.0f}"), lambda v: "white" if (v <= -45 or v >= 14) else INK)
axes[1].set_yticklabels([]); axes[1].tick_params(axis="y", length=0)
cb1 = fig.colorbar(im1, ax=axes[0], fraction=0.035, pad=0.02); cb1.outline.set_visible(False); cb1.ax.tick_params(labelsize=8, length=0)
cb2 = fig.colorbar(im2, ax=axes[1], fraction=0.035, pad=0.02); cb2.outline.set_visible(False); cb2.ax.tick_params(labelsize=8, length=0)
fig.text(0.01, 0.01, "768-token capped inputs, same bytes to every engine. Fine-tuned rows are the mean of three seeds. Typosquat omitted: fine-tuned scores there are template leakage.", fontsize=8, color=INK2)
fig.tight_layout(rect=(0, 0.04, 1, 1)); fig.savefig(f"{OUT}/accuracy-heatmap.png"); plt.close(fig); print("heatmap written")
