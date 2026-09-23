"""Run engines over tasks; one JSONL row per (engine, task, item, run).

  python -m jev_bench.run --engines jev laya:base@cuda:1 laya:typed-decisions@cuda:0 claude:claude-haiku-4-5 \
                          --tasks license typosquat --n 0 --concurrency 4 --runs 1
"""
import argparse, json, os, time, statistics, concurrent.futures as cf
from .tasks import TASK_NAMES, load_task, read_items, write_items
from .engines import load_engine

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engines", nargs="+", required=True)
    ap.add_argument("--tasks", nargs="+", default=TASK_NAMES)
    ap.add_argument("--n", type=int, default=0, help="cap items per task (0 = all)")
    ap.add_argument("--concurrency", type=int, default=1, help="parallel requests for HTTP engines; local Laya is always 1")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="results/raw")
    ap.add_argument("--rebuild", action="store_true", help="rebuild task data instead of reading data/<task>/items.jsonl")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for tname in a.tasks:
        mod = load_task(tname)
        if a.rebuild or not os.path.exists(os.path.join("data", tname, "items.jsonl")):
            write_items(tname, mod.build(0, a.seed))
        items = read_items(tname)
        if a.n: items = items[:a.n]
        for spec in a.engines:
            eng = load_engine(spec)
            conc = 1 if spec.startswith("laya:") else a.concurrency
            path = os.path.join(a.out, f"{eng.name}__{tname}.jsonl")
            with open(path, "a") as out:
                for run in range(a.runs):
                    def one(it):
                        t0 = time.perf_counter()
                        try:
                            ans = eng.answer(it.state, mod.QUESTION, mod.QKEY); err = None
                        except Exception as e:
                            ans, err = None, f"{type(e).__name__}: {str(e)[:300]}"
                        ms = (time.perf_counter() - t0) * 1000
                        return {"engine": eng.name, "task": tname, "run": run, "concurrency": conc, "id": it.id, "label": it.label,
                                "pred": ans.pred if ans else None, "conf": ans.conf if ans else None, "ms": round(ms, 2),
                                "usage": ans.usage if ans else {}, "meta": it.meta, "err": err, "ts": time.time()}
                    t_start = time.perf_counter()
                    if conc > 1:
                        with cf.ThreadPoolExecutor(conc) as ex: rows = list(ex.map(one, items))
                    else:
                        rows = [one(it) for it in items]
                    wall = time.perf_counter() - t_start
                    for r in rows: r["wall_s"] = round(wall, 3); out.write(json.dumps(r) + "\n")
                    ok = [r for r in rows if r["err"] is None]; lat = sorted(r["ms"] for r in ok)
                    acc = sum(r["pred"] == r["label"] for r in ok) / max(1, len(ok))
                    errs = len(rows) - len(ok)
                    print(f"{eng.name:24s} {tname:12s} run={run} n={len(rows)} err={errs} acc={acc:.3f} "
                          f"p50={lat[len(lat)//2] if lat else 0:.0f}ms p95={lat[int(len(lat)*0.95)-1] if lat else 0:.0f}ms "
                          f"thru={len(ok)/wall:.1f}/s (c={conc})", flush=True)
            if hasattr(eng, "agent"): del eng  # free GPU

if __name__ == "__main__":
    main()
