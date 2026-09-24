"""Fair-comparison table: test-split rows from one or more raw dirs, bootstrap 95% CIs, accuracy at a
fixed 80% confidence coverage (threshold chosen per engine/task so that exactly the top 80% most
confident answers are kept), plus latency. Rows are deduped by (engine, task, id); runs (seeds) are
averaged with their spread."""
import glob, json, collections, statistics, os, sys, random
from .analyze import ece, macro_f1, pct, _equiv
from .tasks import split_of

def boot_ci(vals, n=1000, seed=0):
    rng = random.Random(seed); m = len(vals)
    if m == 0: return (float("nan"), float("nan"))
    bs = sorted(statistics.mean(rng.choice(vals) for _ in range(m)) for _ in range(n))
    return bs[int(0.025 * n)], bs[int(0.975 * n)]

def acc_at_coverage(rows, cov=0.8):
    rs = sorted((r for r in rows if r["conf"] is not None), key=lambda r: -r["conf"]); k = max(1, int(len(rs) * cov))
    return statistics.mean(r["pred"] == r["label"] for r in rs[:k]) if rs else float("nan")

def load(dirs):
    rows = []
    for d in dirs:
        for f in glob.glob(os.path.join(d, "*.jsonl")):
            for l in open(f):
                r = json.loads(l); r["meta"].setdefault("split", split_of(r["id"]))
                if r["err"] is None and r["meta"]["split"] == "test": rows.append(r)
    return rows

def main(out="results/fair/summary.md", *dirs):
    dirs = dirs or ("results/fair/raw",)
    rows = load(dirs)
    g = collections.defaultdict(lambda: collections.defaultdict(list))   # (task, engine) -> run -> rows
    for r in rows: g[(r["task"], r["engine"])][r.get("run", 0)].append(r)
    tasks = ["quarantine", "curation", "typosquat", "reachability", "license"]
    engines = sorted({e for _, e in g})
    L = ["| task | engine | n | runs | acc | 95% CI | lenient | macro-F1 | ECE | acc@80%cov | p50 ms | truncated |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    summary = []
    for task in tasks:
        for eng in engines:
            runs = g.get((task, eng))
            if not runs: continue
            per_run = [statistics.mean(r["pred"] == r["label"] for r in rs) for rs in runs.values()]
            allrows = [r for rs in runs.values() for r in rs]
            first = next(iter(runs.values()))
            eq = _equiv(task); lat = sorted(r["ms"] for r in allrows)
            acc = statistics.mean(per_run); sd = statistics.pstdev(per_run) if len(per_run) > 1 else None
            lo, hi = boot_ci([float(r["pred"] == r["label"]) for r in first])
            trunc = statistics.mean(bool(r["meta"].get("truncated")) for r in first)
            rec = dict(task=task, engine=eng, n=len(first), runs=len(runs), acc=acc, acc_sd=sd, ci=(lo, hi),
                       lenient=statistics.mean(eq(r["label"], r["pred"]) for r in allrows) if eq else None,
                       f1=macro_f1(allrows), ece=ece(allrows), acc80=acc_at_coverage(allrows), p50=pct(lat, .5), p95=pct(lat, .95), truncated=trunc)
            summary.append(rec)
            L.append(f"| {task} | {eng} | {rec['n']} | {rec['runs']} | {acc:.3f}{' ±%.3f' % sd if sd is not None else ''} | {lo:.2f}–{hi:.2f} | "
                     f"{('%.3f' % rec['lenient']) if rec['lenient'] is not None else '-'} | {rec['f1']:.3f} | {rec['ece']:.3f} | {rec['acc80']:.3f} | {rec['p50']:.0f} | {trunc:.0%} |")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w").write("\n".join(L) + "\n"); json.dump(summary, open(out.replace(".md", ".json"), "w"), indent=1, default=float); print("\n".join(L))

if __name__ == "__main__":
    main(*sys.argv[1:])
