# We benchmarked four "decision models" on package-curation triage. A 421M model you can fine-tune in 18 minutes beat the hosted one.

*Draft. Numbers marked `[pending]` are being filled from the last two runs.*

## Why

A package registry's curation pipeline asks the same bounded questions thousands of times a day. Is this
package a deliberate impersonation of a popular one? Which license family is this free-text LICENSE? Does this
scanner finding actually reach the declared dependency graph? Why was this artifact quarantined? These are
not generation tasks. They are typed decisions with a small answer space, and the queue that holds them is
human labour. A model that ranks that queue well is pure upside; a wrong answer costs a reorder, not a breach.

In September 2026 a new class of model appeared for exactly this shape of problem. TypeSafe's hosted **Jev**
answers `choice`, `noul` (yes/no) and `score` questions about a state with calibrated probabilities and no
text generation. Within a week, two open alternatives followed: **Laya** (ModernBERT-large, 421M parameters,
Apache 2.0) and Stanford's **CLM-8B** (a frozen Qwen3-8B encoder with a 20M-parameter trained head). All
three speak the same wire format. We wanted to know which one, if any, belongs in our pipeline, and what
happens when its accuracy isn't good enough.

## What we measured

Five tasks modelled on real hot spots in a curation service, 5,561 items, all public or synthetic data:

| Task | Primitive | Where the data comes from |
|---|---|---|
| Quarantine reason | choice, 7 options | templates modelled on ClamAV, Trivy, Grype, ScanCode, OPA, cosign output; 20% carry a distractor |
| Curation review | choice, 4 options | real npm and PyPI metadata; malicious rows from 300 OSV advisories |
| Typosquat second stage | noul | 600 OSV malicious names vs 615 real live near-name packages |
| Finding reachability | noul | real OSV advisories planted in synthetic dependency trees, label by graph walk |
| License family | choice, 8 options | 2,271 real license texts from ScanCode, verbatim, rebranded and truncated |

Seven columns: Jev, Claude Haiku 4.5 as the generative reference, Laya off the shelf (two checkpoints),
Laya fine-tuned, CLM-8B off the shelf, CLM fine-tuned.

## The rules, because they decide the result

Early on we noticed that the comparison was riding on incidental differences: Laya reads 512 or 1,024 tokens,
CLM 2,048, Jev 32k; CLM caches embeddings so repeated states answer in 1 ms; fine-tuned models saw
different renderings of the state than the hosted ones. So we froze a protocol:

1. **Identical bytes.** Every state is rendered to the same `key: value` prose and cut to 768 reference
   tokens (Laya's tokenizer), leaving 256 for the question, so the total fits a 1,024 budget every model can
   read whole. Reachability trees are pruned to the paths that reach the finding's package, for everyone.
2. **Test only.** Every item is assigned train or test by a hash of its id, 80/20. Fine-tunes see train only.
   Every number below is test-split only, for every column, with bootstrap 95% intervals in the repo.
3. **Same tuning data.** One-hot labels from the train split, three seeds each for Laya and CLM, mean and
   spread reported. Temperature refit on a held-out calibration slice for both.
4. **Same latency protocol.** One stream, cold cache, fresh server process, 40 items per task from the same
   client. Hosted engines include network time from a home connection (TLS handshake 145 ms to TypeSafe,
   27 ms to Anthropic, paid once per connection).
5. **Context is its own experiment**, not a confound: after the fair run, Laya was retrained and tested at
   256, 512, 768, 1,536 and 2,048 tokens on the two long-input tasks.
6. **Leakage is labelled, not hidden.** The typosquat positives carry templated README and publisher
   fields (the packages are gone from the registries), and a fine-tuned model learns the template. Those
   cells are marked leaky and excluded from every headline claim.

## Results

| Task | Jev | Haiku 4.5 | Laya (off the shelf) | Laya tuned ×3 | CLM-8B | CLM tuned ×3 |
|---|---|---|---|---|---|---|
| Quarantine reason | 100% | 99% | 80% | 100% ±0.6 | 17% | 100% ±0.6 |
| Curation review | 94% | 97% | 31% | 98% ±0.8 | 19% | 88% ±0.9 |
| Typosquat 2nd stage | 94% | 94% | 53% | 100% ±0.0 (leaky) | 52% | 100% ±0.0 (leaky) |
| Finding reachability | 89% | 59% | 43% | 84% ±5.5 | 44% | 76% ±0.8 |
| License family | 63% | 57% | 23% | 78% ±0.7 | 5% | 58% ±0.6 |
| Latency p50, single stream, cold | 136 ms | 1,154 ms | 21 ms | 21 ms | 116 ms | 116 ms |

What the table says:

**A fine-tuned 421M model matched or beat the hosted model on every honest task, at a tenth of the
latency.** Laya off the shelf was at chance on four of five tasks. Eighteen minutes of training on two RTX
3090s, three times over with different seeds, put it at 99.6% on quarantine (Jev 100%), 98% on curation
(Jev 94%), 84 ±5.5% on reachability (Jev 89%) and 78% on license (Jev 63%), at 21 ms per decision against
136 ms. The reachability gap is inside the noise of 98 test items; the license gap is not, and it goes the
other way.

**License is where fine-tuning does something a hosted model cannot.** Jev and Haiku both sit near 60%
because ScanCode files the Redis and CockroachDB source-available licenses under "Non-Commercial" and plain
permissive notices under "Proprietary Free". No rubric teaches a hosted model those boundaries. Labels do.

**Rubric wording is Jev's real lever, and it is worth 15 points.** With "no release in years" as the
abandoned criterion, Jev called 204 of 300 abandoned packages benign and scored 80% on curation. Restating
it as "last release more than 4 years ago, even when not flagged" took it to 95% on the same items. Haiku
inferred the rule either way. The v1 run is kept as an ablation.

**Jev has one reproducible blind spot.** It got every reachability scenario right except the one where the
vulnerable package sits under both a dev path and a prod path: 0 for 50. It saw "dev" and stopped.
TypeSafe's own docs flag multi-hop conditions; this is what that looks like in a real rubric.

**The generative reference is accurate and slow.** Haiku 4.5 tied Jev on three tasks and lost badly on
reachability (59%, over-confident on dev-only and lookalike findings). At 1.15 s per decision it is 8x Jev
and 50x Laya, and it costs about 25x Jev per token.

**CLM-8B is the one we got wrong the first time, and the bug was ours.** Zero-shot it was at or below chance
on every task: it embeds each rubric option as text and picks the nearest, which does not suit "which of these
seven reasons". A 12-minute head fine-tune helped, but our served numbers were 15 points below CLM's own
evaluation of the same heads. After chasing a tokenization theory that an A/B test refuted (server and training
embeddings were identical for the same text), the cause turned out to be our export: we stored the prose state as
a JSON-quoted string, CLM's loader keeps that as literal text, so the heads trained on `"...\n..."` with escaped
newlines while the server embedded real prose. Same text in, same numbers out. With the export fixed, CLM tuned
scores 99.6% on quarantine, 88.3% on curation, 75.5% on reachability and 57.8% on license (three seeds, spread under 1 point), between off-the-shelf and fine-tuned Laya on every honest task. Its latency is set by the 8B encoder: 56 to 190 ms per fresh capped item
on a 3090, 1 ms on a repeated state from cache. A curation queue almost never repeats a state.

**Context is a real dimension for one task and irrelevant for another.** Laya tuned on reachability:
62% at 256 tokens, 81% at 512, 91% at 768, 86% at 1,536, 80% at 2,048 (the last three are within the noise of 98 items;
the jump is between 256 and 768). License: 78 to 84% at every cap. The dependency tree needs to be seen whole; a license's obligations are in its first page.

**Confidence gating works for Jev today and needs one more step for the fine-tunes.** Jev's calibration
error on quarantine was 0.005, and 86% of its reachability answers came back above 0.9 confidence with 91%
accuracy on that slice. The one-hot fine-tunes came out under-confident because the temperature fit hit its
clamp on 400 calibration items; accuracy at a fixed 80% coverage is still 86 to 100%, but a production
gate wants a bigger calibration slice or a distillation term.

## What others have found

A survey of independent evaluations published in the week since Jev launched (full notes with links in
`docs/related-work.md`) puts our results in context:

- On generic, LLM-authored decision tasks (JevBench, 842 items), Jev still ranks first ahead of every open clone,
  including Laya. Our Laya win is a *fine-tuned* win on *our* tasks, and we say so.
- Tiny in-domain specialists beating hosted Jev is a pattern, not our discovery: a 706k-parameter form-action model
  scored 99.7% vs Jev's 83.6% (CUA-S1); a 150M ModernBERT trained on a GTX 1660 Ti edged Laya and Jev on Laya's own
  suite (openJev-verdict). The academic version predates all of these: RoBERTa/DeBERTa with 200 examples beating
  GPT-4 and Claude Opus zero-shot (Bucher and Martini, 2024).
- Haiku beating Jev on holistic questions and Jev winning once the question is decomposed into atomic ones (Beri,
  phishing: 62.6% vs 81.3% single-question, 95.0% vs 93.2% decomposed) matches our tie on curation and typosquat.
  Our reachability gap (89% vs 59%) is larger than anyone else reports; it is a rule-following task, which is the
  shape decomposition produces.
- Jev's raw probabilities carry about 0.1 calibration error and improve sharply with post-hoc recalibration
  (hn-oracle: 0.105 to 0.017 with isotonic scaling). Ours were 0.005 to 0.13 by task.
- An independent black-box study (Hume) found the same single-pass joint scoring we did, plus option-order
  sensitivity. We checked: reversing option order flipped 0 of 60 quarantine answers, 2 of 60 curation, 4 of 60
  license, with mean probability shifts of 0.002 to 0.05. Milder on our rubrics than reported.
- CLM-8B has never been evaluated on zero-shot text classification by anyone; every published number is action
  scoring over agent trajectories. Our at-chance result is the first such measurement, and it is the wrong task
  for its architecture rather than a flaw in it.
- Nobody has published a decision model or a fine-tuned encoder for package-registry curation. Vendors use classical
  ML for typosquat and metadata (ConfuGuard, in production at Socket) and LLMs for code review (SocketAI).

## What we didn't test

- **Our own queue.** Everything here is public or synthetic. Two of the five tasks are synthetic enough that
  a fine-tune can learn a template. The next step is an export of real review decisions, quarantine events
  and lockfiles through the same harness.
- **Serving under load.** Latency is one stream on a quiet box. A soak test at queue rates with p99 and
  failure behaviour is a separate run. Jev's throughput scaled to 150 decisions/s at 64 streams from one
  test key; Laya's HTTP server does about 60/s per GPU, its batch API over 100/s.
- **CPU deployment.** Laya on a Ryzen 5900X was 270 to 710 ms per item, 15 to 25x the GPU, with a long
  tail on 2k-token inputs. ONNX was not measured.
- **Adversarial inputs.** READMEs are attacker-controlled and neither open model has any injection defence.
- **Non-English packages** and **drift over time**.

## What we'd do with it

Use a hosted model, or Haiku, to bootstrap labels from the review pile, because they start from a written
rule and need nothing else. Then fine-tune Laya on those labels, take the 10x latency and the self-hosting,
and retrain weekly from human overrides. That loop, which the hosted model cannot close, is the actual
advantage. The benchmark says the hand-off works and costs an afternoon.

## Reproduce it

Everything is in `github.com/brandonrc/jev-bench`: task generators with cached public data, the engine
adapters, the fair-mode runner (`--state-cap`), the fine-tune pipeline for Laya (`jev_bench/finetune/`),
the parquet export for CLM's trainer, the latency protocol, the context sweep, the CLM server patch, and
every per-item result under `results/fair/`. Two 3090s reproduce the fine-tunes in under an hour; the
hosted legs cost about 30 cents on Jev and $10 on Haiku.
