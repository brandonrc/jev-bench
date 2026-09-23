import json, os, sys, time, statistics, collections
import httpx
from data import TASKS
import laya

JEV_KEY = os.environ["TYPESAFE_API_KEY"]
jev = httpx.Client(base_url="https://api.typesafe.ai", headers={"Authorization": f"Bearer {JEV_KEY}"}, timeout=60)
agents = {
    "laya-typed": laya.load("convaiinnovations/laya", subfolder="typed-decisions", device="cuda:0"),
    "laya-base":  laya.load("convaiinnovations/laya", device="cuda:1"),
}
print("laya ctx:", {k: a.cfg.get("max_len") for k, a in agents.items()}, flush=True)

def ask_jev(state, q):
    for attempt in range(4):
        r = jev.post("/v1/systemone", json={"model": "jev-latest", "state": state, "questions": q})
        if r.status_code in (429, 529): time.sleep(2 ** attempt); continue
        r.raise_for_status(); return r.json()["answers"]
    raise RuntimeError(r.text)

def decode(ans, qkey):
    a = ans[qkey]
    if a.get("type") == "noul" or "noul" in a:
        p = a["noul"]; return (p >= 0.5, max(p, 1 - p))
    return (a["choice"], a.get("confidence", 0.0))

out = open("pilot_results.jsonl", "w")
summary = collections.defaultdict(lambda: {"n": 0, "correct": 0, "lat": [], "conf_correct": [], "conf_wrong": []})
for tname, (gen, q, qkey) in TASKS.items():
    items = gen()
    for eng in ["jev", "laya-typed", "laya-base"]:
        for it in items:
            t0 = time.perf_counter()
            try:
                ans = ask_jev(it["state"], q) if eng == "jev" else agents[eng].predict(it["state"], q)["answers"]
                pred, conf = decode(ans, qkey); err = None
            except Exception as e:
                pred, conf, err = None, 0.0, str(e)[:200]
            ms = (time.perf_counter() - t0) * 1000
            ok = (pred == it["label"])
            s = summary[(tname, eng)]; s["n"] += 1; s["correct"] += ok; s["lat"].append(ms); (s["conf_correct"] if ok else s["conf_wrong"]).append(conf)
            out.write(json.dumps({"task": tname, "engine": eng, "id": it["id"], "label": it["label"], "pred": pred, "conf": conf, "ms": round(ms, 1), "variant": it.get("variant"), "err": err}) + "\n")
        print(f"{tname:10s} {eng:11s} done", flush=True)
out.close()

print("\n| task | engine | n | acc | p50 ms | p95 ms | mean conf (right) | mean conf (wrong) |")
print("|---|---|---|---|---|---|---|---|")
for (t, e), s in summary.items():
    lat = sorted(s["lat"]); mc = lambda l: f"{statistics.mean(l):.2f}" if l else "-"
    print(f"| {t} | {e} | {s['n']} | {s['correct']/s['n']:.2f} | {lat[len(lat)//2]:.0f} | {lat[int(len(lat)*0.95)-1]:.0f} | {mc(s['conf_correct'])} | {mc(s['conf_wrong'])} |")
