"""Option-order sensitivity: same test items, options in rubric order vs reversed. Reports how often the
top choice flips and how far the top probability moves. Uses the capped prose state like the fair run."""
import os, json, time, statistics, httpx
from jev_bench.tasks import load_task, read_items
from jev_bench.state import prepare_state
K = os.environ["TYPESAFE_API_KEY"]; c = httpx.Client(base_url="https://api.typesafe.ai", headers={"Authorization": f"Bearer {K}"}, timeout=120)
out = open("results/jev_probe.jsonl", "a")
for task in ["quarantine", "curation", "license"]:
    mod = load_task(task); q = mod.QUESTION[mod.QKEY]; items = read_items(task, "test")[:60]
    rev = dict(q); rev["criteria"] = dict(reversed(list(q["criteria"].items())))
    flips = 0; deltas = []; acc_f = acc_r = 0
    for it in items:
        s = prepare_state(task, it.state, 768)[0]
        a = c.post("/v1/systemone", json={"model": "jev-latest", "state": s, "questions": {"q": q}}).json()["answers"]["q"]
        b = c.post("/v1/systemone", json={"model": "jev-latest", "state": s, "questions": {"q": rev}}).json()["answers"]["q"]
        flips += a["choice"] != b["choice"]; deltas.append(abs(a["probabilities"][a["choice"]] - b["probabilities"][a["choice"]]))
        acc_f += a["choice"] == it.label; acc_r += b["choice"] == it.label
    rec = {"probe": "option_order_reversal", "task": task, "n": len(items), "flips": flips, "acc_forward": acc_f/len(items), "acc_reversed": acc_r/len(items), "mean_abs_prob_shift": statistics.mean(deltas), "max_abs_prob_shift": max(deltas), "ts": time.time()}
    out.write(json.dumps(rec) + "\n"); print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in rec.items() if k != "ts"}, flush=True)
