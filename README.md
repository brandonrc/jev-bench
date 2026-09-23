# jev-bench

Head-to-head benchmark of "System One" decision engines on package-registry
triage tasks: the kind of bounded, typed questions a curation pipeline asks
thousands of times a day where a wrong answer costs a queue reorder, not a breach.

**Speed is the headline metric. Accuracy and calibration are secondary.**

| Engine | What it is | Where it runs |
|---|---|---|
| [TypeSafe Jev](https://typesafe.ai) (`jev-latest`) | Hosted non-generative decision model; `choice` / `noul` / `score` primitives with calibrated probabilities | `api.typesafe.ai` |
| [Laya](https://github.com/NandhaKishorM/laya) | Apache-2.0 clone of the same API; ModernBERT-large, 421M params | local GPU (RTX 3090) |
| Claude Haiku 4.5 | Generative LLM forced into the same output shape via structured outputs | Anthropic API |

The three engines get identical state and identical rubrics. Claude answers are
parsed into `{label, confidence}` so every metric is computed the same way.

## Tasks

Modelled on real hot spots in a package-curation service. All data is mock or
public; no proprietary code or data is used.

| Task | Primitive | Ground truth |
|---|---|---|
| License family for non-SPDX LICENSE blobs | choice over 8 families | real SPDX texts, perturbed (rebranded / truncated) |
| Typosquat second stage: deliberate impersonation? | noul | real squat pairs vs real legit affixed packages |
| Curation review: malicious / abandoned / license-incompatible / benign | choice | templated from real package metadata |
| Scanner finding reachability in declared dep graph | noul | graph walk computed in code *(planned)* |
| Quarantine reason | choice | templated scanner output *(planned)* |

## Results (2026-09-23, 1,677 items, single machine)

Shareable report: https://claude.ai/artifact/J3TzPqXzUGnjLgwbJgZAd9

| task | engine | n | acc | lenient | macro-F1 | ECE | cov@0.9 | acc@0.9 | p50 ms | p95 ms | p99 ms | items/s | c |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| license | claude-haiku-4-5 | 807 | 0.646 | 0.773 | 0.649 | 0.192 | 0.42 | 0.871 | 900 | 1347 | 1767 | 8.2 | 8 |
| license | jev | 807 | 0.644 | 0.777 | 0.662 | 0.139 | 0.48 | 0.841 | 185 | 265 | 337 | 20.7 | 4 |
| license | laya-base | 807 | 0.271 | 0.428 | 0.221 | 0.145 | 0.00 | 1.000 | 20 | 26 | 28 | 48.3 | 1 |
| license | laya-typed-decisions | 807 | 0.206 | 0.315 | 0.167 | 0.117 | 0.00 | nan | 24 | 38 | 41 | 35.8 | 1 |
| quarantine | claude-haiku-4-5 | 420 | 0.974 | - | 0.974 | 0.030 | 0.99 | 0.981 | 817 | 1298 | 2531 | 8.4 | 8 |
| quarantine | jev | 420 | 1.000 | - | 1.000 | 0.012 | 0.95 | 1.000 | 171 | 247 | 306 | 22.3 | 4 |
| quarantine | laya-base | 420 | 0.740 | - | 0.752 | 0.417 | 0.00 | 1.000 | 18 | 19 | 19 | 55.4 | 1 |
| quarantine | laya-typed-decisions | 420 | 0.748 | - | 0.736 | 0.672 | 0.00 | nan | 19 | 24 | 25 | 46.7 | 1 |
| reachability | claude-haiku-4-5 | 450 | 0.620 | - | 0.605 | 0.343 | 0.97 | 0.612 | 959 | 1448 | 2118 | 7.6 | 8 |
| reachability | jev | 450 | 0.889 | - | 0.883 | 0.045 | 0.86 | 0.906 | 187 | 250 | 325 | 20.8 | 4 |
| reachability | laya-base | 450 | 0.449 | - | 0.317 | 0.259 | 0.00 | nan | 20 | 21 | 22 | 49.4 | 1 |
| reachability | laya-typed-decisions | 450 | 0.444 | - | 0.308 | 0.202 | 0.00 | nan | 32 | 34 | 35 | 31.8 | 1 |

Per-item rows are in `results/raw/`. Typosquat and curation runs are pending.

## Pilot results (2026-09-23, 166 items, single machine)

| task | engine | n | acc | p50 ms | p95 ms | mean conf (right) | mean conf (wrong) |
|---|---|---|---|---|---|---|---|
| license | jev | 90 | 0.89 | 243 | 362 | 0.97 | 0.58 |
| license | laya-typed | 90 | 0.30 | 21 | 40 | 0.13 | 0.09 |
| license | laya-base | 90 | 0.43 | 20 | 27 | 0.17 | 0.12 |
| typosquat | jev | 36 | 0.97 | 222 | 319 | 0.90 | 0.71 |
| typosquat | laya-typed | 36 | 0.50 | 16 | 17 | 0.58 | 0.57 |
| typosquat | laya-base | 36 | 0.56 | 17 | 17 | 0.58 | 0.55 |
| curation | jev | 40 | 1.00 | 255 | 348 | 1.00 | - |
| curation | laya-typed | 40 | 0.45 | 16 | 18 | 0.12 | 0.12 |
| curation | laya-base | 40 | 0.50 | 17 | 18 | 0.30 | 0.28 |

Jev latency is over the public internet from a home connection with a
keep-alive HTTP client; Laya latency is in-process on one RTX 3090.

Notes so far:

- Jev's license misses are all arguable classifications (Artistic-2.0, OFL-1.1,
  EUPL-1.2, Sleepycat) and all came back with confidence 0.3 to 0.7, versus
  0.97 mean confidence on hits. The confidence signal is usable for gating.
- Laya zero-shot is at chance on these tasks, which its own README warns about
  ("near chance on typed-decisions zero-shot"). It is 12 to 15x faster than Jev
  from here. A fine-tune on task data is the fair comparison and is planned.
- Laya context is 512 tokens (base) or 1024 (typed-decisions); a full GPL text
  is ~8.7k tokens and gets truncated silently.

## Running

```sh
uv venv --python 3.12 .venv && uv pip install -r requirements.txt
export TYPESAFE_API_KEY=...          # never commit this
export ANTHROPIC_API_KEY=...         # or: ant auth login
cd pilot
python run_pilot.py                  # Jev + Laya (needs a CUDA GPU; edit device= for CPU)
python run_claude.py claude-haiku-4-5
```

Results append to `results/pilot_results.jsonl`.

## Credentials

Keys are read from the environment only. Nothing under this repo should ever
contain a key; `.env` and `*.key` are gitignored.

## Layout

```
jev_bench/tasks/      one module per task: QUESTION, QKEY, build(n, seed) -> data/<task>/items.jsonl
jev_bench/engines/    jev (HTTP), laya (in-process or laya-serve), claude (structured outputs)
jev_bench/run.py      python -m jev_bench.run --engines jev laya:base@cuda:1 claude:claude-haiku-4-5 --tasks license ...
jev_bench/analyze.py  results/raw/*.jsonl -> results/summary.md (accuracy, macro-F1, ECE, coverage@0.9, p50/p95/p99, items/s)
jev_bench/speed.py    concurrency sweep, Jev multi-question fan-out, Laya batch inference
scripts/netcheck.sh   TCP + TLS handshake time to each API host, to separate network from inference
pilot/                the first 166-item pilot, kept as-is
```
