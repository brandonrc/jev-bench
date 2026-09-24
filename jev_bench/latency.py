"""Single-stream, cold-cache latency protocol, identical for every engine.

  python -m jev_bench.latency --engines jev claude:claude-haiku-4-5 laya:/path@cuda:0 clm-http:http://localhost:8700#clm-ft \
                              --n 40 --state-cap 768 --out results/fair/latency.jsonl

One request at a time, the first N test items of each task (never seen by a fresh server process),
2 warm-up calls on items outside the sample, client-side wall clock plus server-side time where the
engine reports it. Hosted engines additionally get a TCP/TLS handshake sample from `scripts/netcheck.sh`."""
import argparse, json, time, statistics
from .engines import load_engine
from .tasks import TASK_NAMES, load_task, read_items
from .state import prepare_state

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--engines", nargs="+", required=True); ap.add_argument("--tasks", nargs="+", default=["quarantine", "curation", "typosquat", "reachability", "license"])
    ap.add_argument("--n", type=int, default=40); ap.add_argument("--state-cap", type=int, default=None); ap.add_argument("--out", default="results/fair/latency.jsonl"); a = ap.parse_args()
    out = open(a.out, "a")
    for spec in a.engines:
        eng = load_engine(spec)
        for task in a.tasks:
            mod = load_task(task); items = read_items(task, "test")
            sample, warm = items[:a.n], items[a.n:a.n + 2]
            st = lambda it: prepare_state(task, it.state, a.state_cap)[0] if a.state_cap else it.state
            for it in warm:
                try: eng.answer(st(it), mod.QUESTION, mod.QKEY)
                except Exception: pass
            lat, srv, errs = [], [], 0
            for it in sample:
                s = st(it); t = time.perf_counter()
                try:
                    ans = eng.answer(s, mod.QUESTION, mod.QKEY); lat.append((time.perf_counter() - t) * 1000)
                    v = ans.usage.get("server_ms") if ans.usage else None
                    if v is not None and v == v: srv.append(v)
                except Exception: errs += 1
            lat.sort()
            rec = {"engine": eng.name, "task": task, "mode": "single-stream,cold", "n": len(lat), "errors": errs, "state_cap": a.state_cap,
                   "p50_ms": lat[len(lat) // 2] if lat else None, "p95_ms": lat[int(len(lat) * .95) - 1] if lat else None, "mean_ms": statistics.mean(lat) if lat else None,
                   "server_p50_ms": sorted(srv)[len(srv) // 2] if srv else None, "ts": time.time()}
            out.write(json.dumps(rec) + "\n"); print(f"{rec['engine']:22s} {task:13s} p50={rec['p50_ms'] or 0:7.1f}ms p95={rec['p95_ms'] or 0:7.1f}ms n={rec['n']} err={errs}", flush=True)
        if hasattr(eng, "agent"): del eng

if __name__ == "__main__":
    main()
