"""Aggregate results/raw/*.jsonl into results/summary.md (+ summary.json)."""
import glob, json, collections, statistics, math, os, sys, importlib

def _equiv(task):
    try: return getattr(importlib.import_module(f"jev_bench.tasks.{task}"), "equivalent", None)
    except Exception: return None

def ece(rows, bins=10):
    """Expected calibration error on P(pred)."""
    b = [[] for _ in range(bins)]
    for r in rows:
        if r["conf"] is None: continue
        i = min(bins - 1, int(r["conf"] * bins)); b[i].append((r["conf"], r["pred"] == r["label"]))
    n = sum(len(x) for x in b); tot = 0.0
    for x in b:
        if x: tot += len(x) / n * abs(statistics.mean(c for c, _ in x) - statistics.mean(o for _, o in x))
    return tot

def macro_f1(rows):
    labels = {str(r["label"]) for r in rows} | {str(r["pred"]) for r in rows if r["pred"] is not None}
    f1s = []
    for L in labels:
        tp = sum(str(r["pred"]) == L and str(r["label"]) == L for r in rows)
        fp = sum(str(r["pred"]) == L and str(r["label"]) != L for r in rows)
        fn = sum(str(r["pred"]) != L and str(r["label"]) == L for r in rows)
        if tp + fn == 0: continue
        p = tp / (tp + fp) if tp + fp else 0; rc = tp / (tp + fn)
        f1s.append(0 if p + rc == 0 else 2 * p * rc / (p + rc))
    return statistics.mean(f1s) if f1s else 0

def coverage(rows, thr=0.9):
    hi = [r for r in rows if r["conf"] is not None and r["conf"] >= thr]
    return len(hi) / len(rows), (statistics.mean(r["pred"] == r["label"] for r in hi) if hi else float("nan"))

def pct(lat, p): return lat[min(len(lat) - 1, int(len(lat) * p))] if lat else float("nan")

def main(raw="results/raw", out="results"):
    rows = [json.loads(l) for f in glob.glob(os.path.join(raw, "*.jsonl")) for l in open(f)]
    groups = collections.defaultdict(list)
    for r in rows: groups[(r["task"], r["engine"])].append(r)
    summary = []
    for (task, eng), rs in sorted(groups.items()):
        ok = [r for r in rs if r["err"] is None]; lat = sorted(r["ms"] for r in ok)
        cov, cov_acc = coverage(ok)
        tok_in = sum(r["usage"].get("input_tokens", 0) for r in ok); tok_out = sum(r["usage"].get("output_tokens", 0) for r in ok)
        thru = statistics.mean({r["run"]: len([x for x in rs if x["run"] == r["run"]]) / r["wall_s"] for r in rs}.values())
        by_meta = collections.defaultdict(list)
        for r in ok:
            for k in ("variant", "scenario", "hard", "relation", "source"):
                if k in r["meta"]: by_meta[f"{k}={r['meta'][k]}"].append(r["pred"] == r["label"])
        eq = _equiv(task)
        summary.append({"task": task, "engine": eng, "n": len(rs), "errors": len(rs) - len(ok),
                        "lenient_accuracy": statistics.mean(eq(r["label"], r["pred"]) for r in ok) if (ok and eq) else None,
                        "accuracy": statistics.mean(r["pred"] == r["label"] for r in ok) if ok else float("nan"),
                        "macro_f1": macro_f1(ok), "ece": ece(ok), "coverage@0.9": cov, "acc@0.9": cov_acc,
                        "p50_ms": pct(lat, .5), "p95_ms": pct(lat, .95), "p99_ms": pct(lat, .99), "throughput_per_s": thru,
                        "concurrency": rs[0]["concurrency"], "tokens_in": tok_in, "tokens_out": tok_out,
                        "slices": {k: round(statistics.mean(v), 3) for k, v in sorted(by_meta.items())}})
    os.makedirs(out, exist_ok=True)
    json.dump(summary, open(os.path.join(out, "summary.json"), "w"), indent=1)
    L = ["| task | engine | n | acc | lenient | macro-F1 | ECE | cov@0.9 | acc@0.9 | p50 ms | p95 ms | p99 ms | items/s | c |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in summary:
        L.append(f"| {s['task']} | {s['engine']} | {s['n']} | {s['accuracy']:.3f} | {('%.3f' % s['lenient_accuracy']) if s['lenient_accuracy'] is not None else '-'} | {s['macro_f1']:.3f} | {s['ece']:.3f} | {s['coverage@0.9']:.2f} | {s['acc@0.9']:.3f} | "
                 f"{s['p50_ms']:.0f} | {s['p95_ms']:.0f} | {s['p99_ms']:.0f} | {s['throughput_per_s']:.1f} | {s['concurrency']} |")
    L.append("\n## Slices (accuracy by meta field)\n")
    for s in summary:
        if s["slices"]: L.append(f"- **{s['task']} / {s['engine']}**: " + ", ".join(f"{k} {v}" for k, v in s["slices"].items()))
    open(os.path.join(out, "summary.md"), "w").write("\n".join(L) + "\n"); print("\n".join(L))

if __name__ == "__main__":
    main(*sys.argv[1:])
