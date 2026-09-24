"""Probe Jev's internals from the outside: how latency and billed tokens respond to
(a) option count, (b) option-name length, (c) state length, (d) questions per call, (e) exact repeats.
Single stream, keep-alive, N reps per point, medians reported. Writes results/jev_probe.jsonl."""
import os, time, json, statistics, httpx, random
K = os.environ["TYPESAFE_API_KEY"]; c = httpx.Client(base_url="https://api.typesafe.ai", headers={"Authorization": f"Bearer {K}"}, timeout=120)
random.seed(1); out = open("results/jev_probe.jsonl", "a")
WORDS = "package registry maintainer release license script install download credential telemetry archive mirror checksum signature policy scanner advisory dependency version publisher readme".split()
def state_of(n_tokens):  # ~1 token per word for this vocabulary
    return "package metadata: " + " ".join(random.choice(WORDS) for _ in range(max(1, n_tokens - 3)))
def call(state, questions, reps=12):
    lat, it, ot = [], [], []
    for _ in range(reps):
        t = time.perf_counter(); r = c.post("/v1/systemone", json={"model": "jev-latest", "state": state, "questions": questions}); r.raise_for_status()
        lat.append((time.perf_counter() - t) * 1000); u = r.json()["usage"]; it.append(u["input_tokens"]); ot.append(u["output_tokens"])
    lat.sort(); return {"p50_ms": lat[len(lat)//2], "min_ms": lat[0], "in_tok": statistics.median(it), "out_tok": statistics.median(ot)}
def rec(**kw): kw["ts"] = time.time(); out.write(json.dumps(kw) + "\n"); print({k: (round(v, 1) if isinstance(v, float) else v) for k, v in kw.items() if k != "ts"}, flush=True)
c.post("/v1/systemone", json={"model": "jev-latest", "state": "warm", "questions": {"q": {"type": "noul", "instructions": "Is this a package?"}}})

print("--- (a) option count, fixed 300-token state, short option names")
S = state_of(300)
for n in [2, 4, 8, 16, 32, 64]:
    q = {"pick": {"type": "choice", "instructions": "Which category best fits this package?", "criteria": {f"cat{i}": f"category number {i}" for i in range(n)}}}
    rec(probe="option_count", n_options=n, **call(S, q))
print("--- (b) option-name length, 8 options, same descriptions")
for L, name in [(1, "short"), (12, "medium"), (40, "long")]:
    q = {"pick": {"type": "choice", "instructions": "Which category best fits this package?", "criteria": {("k" * L) + str(i): f"category number {i}" for i in range(8)}}}
    rec(probe="option_name_len", name_len=L, **call(S, q))
print("--- (c) state length, 4 options")
q4 = {"pick": {"type": "choice", "instructions": "Which category best fits this package?", "criteria": {f"cat{i}": f"category number {i}" for i in range(4)}}}
for n in [50, 300, 1000, 3000, 8000, 16000]:
    rec(probe="state_len", state_tokens=n, **call(state_of(n), q4, reps=8))
print("--- (d) questions per call, 300-token state, 4 options each")
for n in [1, 2, 5, 10, 20]:
    qs = {f"q{i}": {"type": "choice", "instructions": f"Which category best fits aspect {i} of this package?", "criteria": {f"cat{j}": f"category number {j}" for j in range(4)}} for i in range(n)}
    rec(probe="questions_per_call", n_questions=n, **call(S, qs))
print("--- (e) exact repeat vs fresh state, 1000 tokens, 4 options")
S1 = state_of(1000); rec(probe="repeat_same_state", **call(S1, q4, reps=20))
rec(probe="fresh_state_each_call", **{k: v for k, v in zip(["p50_ms", "min_ms", "in_tok", "out_tok"], (lambda L: (sorted(x[0] for x in L)[len(L)//2], min(x[0] for x in L), statistics.median(x[1] for x in L), statistics.median(x[2] for x in L)))([(lambda r0, t0: ((time.perf_counter() - t0) * 1000, r0["usage"]["input_tokens"], r0["usage"]["output_tokens"]))(c.post("/v1/systemone", json={"model": "jev-latest", "state": state_of(1000), "questions": q4}).json(), time.perf_counter()) for _ in range(20)]))})
