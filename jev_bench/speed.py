"""Speed-only experiments on a fixed item set: concurrency sweep, Jev fan-out (many questions per call), Laya batch.

  python -m jev_bench.speed --task curation --n 100 --jev-concurrency 1 4 16 --laya-devices cuda:0 cuda:1
"""
import argparse, json, os, time, statistics, concurrent.futures as cf
from .tasks import load_task, read_items
from .engines import load_engine

def pct(l, p): l = sorted(l); return l[min(len(l) - 1, int(len(l) * p))]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="curation"); ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--jev-concurrency", nargs="*", type=int, default=[1, 4, 16])
    ap.add_argument("--claude", nargs="*", default=[], help="claude model ids to sweep at concurrency 1 and 8")
    ap.add_argument("--laya-devices", nargs="*", default=["cuda:0"])
    ap.add_argument("--out", default="results/speed.jsonl")
    a = ap.parse_args()
    mod = load_task(a.task); items = read_items(a.task)[:a.n]; states = [it.state for it in items]
    out = open(a.out, "a")
    def rec(**kw): kw.update(task=a.task, n=len(items), ts=time.time()); out.write(json.dumps(kw) + "\n"); print(kw, flush=True)

    if os.environ.get("TYPESAFE_API_KEY"):
        jev = load_engine("jev")
        for c in a.jev_concurrency:
            t0 = time.perf_counter(); lat = []
            def one(s):
                t = time.perf_counter(); jev.answer(s, mod.QUESTION, mod.QKEY); return (time.perf_counter() - t) * 1000
            with cf.ThreadPoolExecutor(c) as ex: lat = list(ex.map(one, states))
            wall = time.perf_counter() - t0
            rec(engine="jev", mode=f"concurrency={c}", p50_ms=pct(lat, .5), p95_ms=pct(lat, .95), items_per_s=len(items) / wall)
        # fan-out: same question asked 5x under different keys == 5 decisions per call
        qs = {f"{mod.QKEY}_{i}": mod.QUESTION[mod.QKEY] for i in range(5)}
        lat = []
        for s in states[:40]:
            t = time.perf_counter(); jev.answer_multi(s, qs); lat.append((time.perf_counter() - t) * 1000)
        rec(engine="jev", mode="fanout_5q_per_call", p50_ms=pct(lat, .5), p95_ms=pct(lat, .95), decisions_per_s=5 * 40 / (sum(lat) / 1000))

    for dev in a.laya_devices:
        for ck in ("base", "typed-decisions"):
            eng = load_engine(f"laya:{ck}@{dev}")
            for _ in range(3): eng.answer(states[0], mod.QUESTION, mod.QKEY)
            lat = []
            for s in states:
                t = time.perf_counter(); eng.answer(s, mod.QUESTION, mod.QKEY); lat.append((time.perf_counter() - t) * 1000)
            rec(engine=eng.name, mode=f"single@{dev}", p50_ms=pct(lat, .5), p95_ms=pct(lat, .95), items_per_s=1000 / statistics.mean(lat))
            for bs in (16, 64):
                t = time.perf_counter(); eng.answer_batch(states, mod.QUESTION, mod.QKEY, batch_size=bs); wall = time.perf_counter() - t
                rec(engine=eng.name, mode=f"batch{bs}@{dev}", ms_per_item=1000 * wall / len(items), items_per_s=len(items) / wall)
            del eng

    for m in a.claude:
        eng = load_engine(f"claude:{m}")
        for c in (1, 8):
            t0 = time.perf_counter()
            def one(s):
                t = time.perf_counter(); eng.answer(s, mod.QUESTION, mod.QKEY); return (time.perf_counter() - t) * 1000
            with cf.ThreadPoolExecutor(c) as ex: lat = list(ex.map(one, states))
            wall = time.perf_counter() - t0
            rec(engine=m, mode=f"concurrency={c}", p50_ms=pct(lat, .5), p95_ms=pct(lat, .95), items_per_s=len(items) / wall)

if __name__ == "__main__":
    main()
