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
| Laya, fine-tuned | Same model after 4 epochs on the train splits (`jev_bench/finetune/`) | local GPU |
| [CLM-8B](https://github.com/Contrastive-LM/CLM) | Frozen Qwen3-8B encoder + 20M projection head, dot-product scoring, same wire format; zero-shot and with a head fine-tuned on the train splits | local GPU via vLLM |

The three engines get identical state and identical rubrics. Claude answers are
parsed into `{label, confidence}` so every metric is computed the same way.

## Tasks

Modelled on real hot spots in a package-curation service. All data is mock or
public; no proprietary code or data is used.

| Task | Primitive | Ground truth |
|---|---|---|
| License family for non-SPDX LICENSE blobs | choice over 8 families | real SPDX texts, perturbed (rebranded / truncated) |
| Typosquat second stage: deliberate impersonation? | noul | 600 OSV malicious names vs 615 real live near-name packages |
| Curation review: malicious / abandoned / license-incompatible / benign | choice | real npm/PyPI metadata; malicious rows from 300 OSV advisories |
| Scanner finding reachability in declared dep graph | noul | real OSV advisories in synthetic graphs, label by graph walk |
| Quarantine reason | choice | templated scanner output, 7 reasons, 20% with distractors |

## Results (fair protocol, 2026-09-24)

Shareable reports: [main benchmark](https://claude.ai/artifact/J3TzPqXzUGnjLgwbJgZAd9) · [Laya fine-tune](https://claude.ai/artifact/D6AT7VLuRVBDuQQKSD1Ym1)
Write-ups: `docs/blog-phase1.md` (first person), `docs/blog-draft.md` (technical), `docs/related-work.md` (survey).

Every engine gets the same 768-token capped prose state (`--state-cap 768`), every number is on the held-out test
split, fine-tunes are three seeds, latency is single-stream cold in a fresh process. Typosquat fine-tuned cells are
template leakage and excluded from claims.

| Task | Jev | Haiku 4.5 | Laya (off the shelf) | Laya tuned ×3 | CLM-8B | CLM tuned ×3 |
|---|---|---|---|---|---|---|
| Quarantine reason | 100% | 99% | 80% | 100% ±0.6 | 17% | 100% ±0.6 |
| Curation review | 94% | 97% | 31% | 98% ±0.8 | 19% | 88% ±0.9 |
| Typosquat 2nd stage | 94% | 94% | 53% | 100% ±0.0 (leaky) | 52% | 100% ±0.0 (leaky) |
| Finding reachability | 89% | 59% | 43% | 84% ±5.5 | 44% | 76% ±0.8 |
| License family | 63% | 57% | 23% | 78% ±0.7 | 5% | 58% ±0.6 |
| Latency p50, single stream, cold | 136 ms | 1154 ms | 21 ms | 21 ms | 116 ms | – |

Full table with intervals, macro-F1, ECE and accuracy at 80% coverage (`results/fair/summary.md`):

| task | engine | n | runs | acc | 95% CI | lenient | macro-F1 | ECE | acc@80%cov | p50 ms | truncated |
|---|---|---|---|---|---|---|---|---|---|---|---|
| quarantine | claude-haiku-4-5 | 82 | 1 | 0.988 | 0.95–1.00 | - | 0.988 | 0.043 | 0.985 | 1213 | 0% |
| quarantine | clm-8b | 82 | 1 | 0.171 | 0.10–0.26 | - | 0.085 | 0.461 | 0.200 | 2 | 0% |
| quarantine | clm-ft | 82 | 3 | 0.996 ±0.006 | 0.96–1.00 | - | 0.996 | 0.077 | 1.000 | 51 | 0% |
| quarantine | jev | 82 | 1 | 1.000 | 1.00–1.00 | - | 1.000 | 0.005 | 1.000 | 155 | 0% |
| quarantine | laya-base | 82 | 1 | 0.768 | 0.67–0.87 | - | 0.778 | 0.532 | 0.785 | 19 | 0% |
| quarantine | laya-ft | 82 | 3 | 0.996 ±0.006 | 0.96–1.00 | - | 0.996 | 0.061 | 1.000 | 20 | 0% |
| quarantine | laya-typed-decisions | 82 | 1 | 0.805 | 0.72–0.89 | - | 0.794 | 0.742 | 0.846 | 19 | 0% |
| curation | claude-haiku-4-5 | 240 | 1 | 0.967 | 0.94–0.99 | - | 0.968 | 0.043 | 1.000 | 1177 | 0% |
| curation | clm-8b | 240 | 1 | 0.188 | 0.14–0.24 | - | 0.104 | 0.432 | 0.193 | 4 | 0% |
| curation | clm-ft | 240 | 3 | 0.883 ±0.009 | 0.85–0.93 | - | 0.877 | 0.102 | 0.953 | 245 | 0% |
| curation | jev | 240 | 1 | 0.942 | 0.91–0.97 | - | 0.941 | 0.037 | 0.990 | 141 | 0% |
| curation | laya-base | 240 | 1 | 0.292 | 0.23–0.35 | - | 0.195 | 0.113 | 0.339 | 17 | 0% |
| curation | laya-ft | 240 | 3 | 0.981 ±0.008 | 0.95–0.99 | - | 0.979 | 0.046 | 0.998 | 17 | 0% |
| curation | laya-typed-decisions | 240 | 1 | 0.312 | 0.25–0.38 | - | 0.238 | 0.249 | 0.328 | 18 | 0% |
| typosquat | claude-haiku-4-5 | 248 | 1 | 0.935 | 0.90–0.96 | - | 0.935 | 0.083 | 0.980 | 1199 | 0% |
| typosquat | clm-8b | 248 | 1 | 0.516 | 0.45–0.58 | - | 0.403 | 0.260 | 0.571 | 4 | 0% |
| typosquat | clm-ft | 248 | 3 | 1.000 ±0.000 | 1.00–1.00 | - | 1.000 | 0.027 | 1.000 | 221 | 0% |
| typosquat | jev | 248 | 1 | 0.944 | 0.92–0.97 | - | 0.943 | 0.103 | 1.000 | 138 | 0% |
| typosquat | laya-base | 248 | 1 | 0.375 | 0.31–0.44 | - | 0.308 | 0.252 | 0.379 | 17 | 0% |
| typosquat | laya-ft | 248 | 3 | 1.000 ±0.000 | 1.00–1.00 | - | 1.000 | 0.003 | 1.000 | 16 | 0% |
| typosquat | laya-typed-decisions | 248 | 1 | 0.528 | 0.47–0.59 | - | 0.387 | 0.033 | 0.535 | 16 | 0% |
| reachability | claude-haiku-4-5 | 98 | 1 | 0.592 | 0.49–0.69 | - | 0.566 | 0.373 | 0.577 | 1245 | 10% |
| reachability | clm-8b | 98 | 1 | 0.439 | 0.35–0.54 | - | 0.320 | 0.366 | 0.462 | 4 | 10% |
| reachability | clm-ft | 98 | 3 | 0.755 ±0.008 | 0.68–0.85 | - | 0.747 | 0.035 | 0.804 | 452 | 10% |
| reachability | jev | 98 | 1 | 0.888 | 0.83–0.95 | - | 0.880 | 0.075 | 0.962 | 145 | 10% |
| reachability | laya-base | 98 | 1 | 0.429 | 0.34–0.53 | - | 0.300 | 0.265 | 0.423 | 19 | 10% |
| reachability | laya-ft | 98 | 3 | 0.844 ±0.055 | 0.68–0.85 | - | 0.838 | 0.063 | 0.902 | 23 | 10% |
| reachability | laya-typed-decisions | 98 | 1 | 0.429 | 0.34–0.53 | - | 0.300 | 0.230 | 0.513 | 20 | 10% |
| license | claude-haiku-4-5 | 423 | 1 | 0.574 | 0.52–0.62 | 0.697 | 0.565 | 0.238 | 0.642 | 1141 | 45% |
| license | clm-8b | 423 | 1 | 0.052 | 0.03–0.07 | 0.222 | 0.029 | 0.687 | 0.044 | 8 | 45% |
| license | clm-ft | 423 | 3 | 0.578 ±0.006 | 0.52–0.62 | 0.650 | 0.562 | 0.085 | 0.625 | 466 | 45% |
| license | jev | 423 | 1 | 0.626 | 0.58–0.67 | 0.764 | 0.629 | 0.114 | 0.686 | 153 | 45% |
| license | laya-base | 423 | 1 | 0.281 | 0.24–0.32 | 0.402 | 0.249 | 0.137 | 0.322 | 20 | 45% |
| license | laya-ft | 423 | 3 | 0.781 ±0.007 | 0.75–0.83 | 0.815 | 0.754 | 0.118 | 0.863 | 30 | 45% |
| license | laya-typed-decisions | 423 | 1 | 0.229 | 0.19–0.27 | 0.300 | 0.164 | 0.138 | 0.234 | 26 | 45% |

Context sweep (Laya retrained per cap, `results/fair/context/`): reachability 62 / 81 / 91 / 86 / 80% and license
78 / 84 / 79 / 82 / 78% at 256 / 512 / 768 / 1,536 / 2,048 tokens. Jev probes: `results/jev_probe.jsonl`.
Earlier uncapped runs remain under `results/raw/`, `results/raw-ft/` and `results/summary_test.md`.

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
