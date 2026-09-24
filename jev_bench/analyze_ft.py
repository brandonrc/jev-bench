"""Fair comparison on the held-out TEST split only: hosted engines' rows filtered to meta.split=='test',
fine-tuned Laya rows from results/raw-ft (which were run with --split test)."""
import glob, json, collections, statistics, os, sys
from .analyze import ece, macro_f1, coverage, pct, _equiv
from .tasks import split_of

def load(pattern, split_filter):
    rows = [json.loads(l) for f in glob.glob(pattern) for l in open(f)]
    for r in rows: r["meta"].setdefault("split", split_of(r["id"]))   # older runs predate the split field
    return [r for r in rows if r["err"] is None and (not split_filter or r["meta"]["split"] == "test")]

def main(out="results/summary_test.md"):
    rows = load("results/raw/*.jsonl", True) + load("results/raw-ft/*.jsonl", True)
    seen = set(); rows = [r for r in rows if not ((r["engine"], r["task"], r["id"]) in seen or seen.add((r["engine"], r["task"], r["id"])))]
    g = collections.defaultdict(list)
    for r in rows: g[(r["task"], r["engine"])].append(r)
    order = ["jev", "claude-haiku-4-5", "laya-base", "laya-typed-decisions", "laya-ft-all-onehot", "laya-ft-all-distill", "laya-ft-all5-onehot"]
    L = ["| task | engine | n (test) | acc | lenient | macro-F1 | ECE | cov@0.9 | acc@0.9 | p50 ms |", "|---|---|---|---|---|---|---|---|---|---|"]
    summary = []
    for task in ["license", "reachability", "quarantine", "curation", "typosquat"]:
        for eng in order:
            rs = g.get((task, eng))
            if not rs: continue
            lat = sorted(r["ms"] for r in rs); cov, acc90 = coverage(rs); eq = _equiv(task)
            acc = statistics.mean(r["pred"] == r["label"] for r in rs)
            len_acc = statistics.mean(eq(r["label"], r["pred"]) for r in rs) if eq else None
            summary.append(dict(task=task, engine=eng, n=len(rs), acc=acc, lenient=len_acc, f1=macro_f1(rs), ece=ece(rs), cov=cov, acc90=acc90, p50=pct(lat, .5)))
            L.append(f"| {task} | {eng} | {len(rs)} | {acc:.3f} | {('%.3f' % len_acc) if len_acc is not None else '-'} | {macro_f1(rs):.3f} | {ece(rs):.3f} | {cov:.2f} | {acc90:.3f} | {pct(lat,.5):.0f} |")
    open(out, "w").write("\n".join(L) + "\n"); json.dump(summary, open(out.replace(".md", ".json"), "w"), indent=1); print("\n".join(L))

if __name__ == "__main__":
    main(*sys.argv[1:])
