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
- The Claude leg has not run yet: it needs an Anthropic Console credential.

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
