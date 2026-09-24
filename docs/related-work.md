# Related work and independent evaluations (research pass, 2026-09-24)

Compiled from ~40 sources by a web research pass. Nothing here was measured by us unless stated; vendor-reported
numbers are labelled. Where nothing was found, it says so.

## 1. Independent evaluations of Jev-class models since September 2026

- **JevBench** (F. Standhartinger / Benchmark Heaven): [repo](https://github.com/fstandhartinger/jevbench),
  [leaderboard](https://benchmarkheaven.com/jev-models), [Show HN](https://news.ycombinator.com/item?id=49800574).
  534 frozen + 308 sealed LLM-authored decisions (routing, adequacy, policy, intent, severity, enum extraction).
  Jev 1.13.0 ranks first (74.4); open re-creations Winnow-12B 71.2, reflex-4B 70.3, then Hopper, Laya, Kev, OpenJev.
  Latency 0.1 to 0.5 s, $0.04 per 1k decisions. *Takeaway: on generic tasks Jev still leads open clones; our
  fine-tuned-Laya win is task-specific.*
- **LangChain, Jev as agent evaluator** ([blog](https://www.langchain.com/blog/jev-agent-evals-langsmith), 2026-09-20;
  [repro](https://github.com/danielgshea/jev-as-a-judge)). 5 runs x 100 reps: Jev 100% human agreement, GPT-5.6 Terra
  99.8%, Claude Sonnet 4.6 80%; 92 to 913x lower variance; 0.44 s vs 2.2 to 2.8 s; $0.34 vs $28.17. Authors call it narrow.
- **Beri, phishing** ([article](https://www.beri.net/article/typesafe-jev-typed-decision-model-calibration-decomposition-shadow-eval),
  2026-09-17). 2,000 synthetic emails: single question Jev 62.6% vs Haiku 4.5 81.3%; decomposed into 5 atomic questions
  plus logistic regression, Jev 95.0% vs Haiku 93.2%. Latency 239 vs 687 ms. Support-ticket ECE 0.107; choice/score
  over-confident, noul under-confident. *Takeaway: Haiku can beat Jev on holistic questions; decomposition matters.
  Agrees with our ties, disagrees with our reachability gap.*
- **Empryo, API-failure retry/halt** ([post](https://empryo.com/blog/jev-and-the-harness), 2026-09-16). 102 real
  failures: Jev 102/102, Terra/Luna 102/102, Haiku 101/102, regex 98/102; 273 ms median.
- **hn-oracle** ([repo](https://github.com/anthony-maio/hn-oracle), 2026-09-23). Pre-registered. Recall 0.92; raw ECE
  0.105, 0.017 after isotonic recalibration; F1 0.76 vs Sonnet 5 0.74 at 1/70 cost, 1/10 latency. *Takeaway: Jev's raw
  probabilities benefit from post-hoc recalibration; consistent with Beri and with Laya's report of Jev ECE 0.144.*
- **Archer Hume, "Jev's Architecture Unmasked"** ([post](https://archerhume.com/posts/jevs-architecture-unmasked/),
  2026-09-17). 10k+ black-box calls, 192 latency samples; MMLU-Pro sample 84.6% with ECE 0.031; adding an irrelevant
  option shifts odds between existing options (-0.28 log-odds, 95% CI -0.36 to -0.19); reversing option order moves
  probabilities 0.84 to 0.89 up to 0.93 to 0.96. Tokenizer closest to Qwen but not identical. *Takeaway: independently
  confirms single-pass joint scoring; documents order sensitivity.*
- **Laya README** ([repo](https://github.com/NandhaKishorM/laya)) on the synthetic
  [typed-decisions](https://huggingface.co/datasets/LocalLLaMA/typed-decisions) set: laya-typed-decisions 0.766 /
  Brier 0.062 / ECE 0.081 vs Jev 0.727 / 0.148 / 0.144; 32.8 ms on T4 vs Jev p50 236 to 276 ms. Vendor-reported.
- **openJev-verdict-2.0** ([repo](https://github.com/Heman10x-NGU/openJev-verdict-2.0),
  [model](https://huggingface.co/heman10x/rlcd-modernbert-151m)). ModernBERT-base 150M, 8.8 h on a GTX 1660 Ti:
  77.1% / ECE 0.014 / 20 to 25 ms on the same set.
- **laya-mlx** ([repo](https://github.com/mizorewww/laya-mlx)): 7.4 to 13.4 ms on M3 Max, fidelity-only validation.
- **CLM-8B** ([coverage](https://www.marktechpost.com/2026/09/23/contrastive-lm-releases-clm-8b-an-open-system-one-model-that-scores-agent-actions-up-to-9x-faster-than-jev/),
  [repo](https://github.com/Contrastive-LM/CLM)). Versus Jev: tool-calling 95.2% vs 99.2%, WikiRacing 26/30 vs 30/30,
  T-Rex and Mario 5/5 both; 16 to 80 ms vs 125 to 225 ms; fine-tuned verifier DeepSWE 81.6% vs 71.1%. All tasks are
  action scoring over agent trajectories; **no zero-shot text-classification evaluation exists.**
- **Kev** ([repo](https://github.com/jaredpalmer/kev)): Qwen3.5 LoRA r=16 plus pointer head; Kev-27B 0.848 vs Jev 0.857
  on new-source questions; Kev-4B 18 ms on H100.
- **CUA-S1** ([Show HN](https://news.ycombinator.com/item?id=49767564)): 706k-parameter form-action model 99.7% vs
  Jev 83.6%; 7 to 9 ms vs 260 to 280 ms. *Same pattern as ours: a tiny in-domain specialist beats hosted Jev.*
- **Open-Jev on CallScreenBench** ([arXiv 2609.23959](https://arxiv.org/abs/2609.23959), 2026-09-21): Qwen3-4B LoRA
  single-pass readout, AUROC 0.974, calibration error 0.052, 64.5 ms.
- **KDnuggets critique** ([Awan, 2026-09-21](https://www.kdnuggets.com/what-everyone-is-getting-wrong-about-typesafe-ais-jev)):
  Jev is an optimised classifier, not a new kind of AI; public evals are small.
- Also: [daf-jev toolkit](https://zenodo.org/records/22921974) (batching ~18x speedup), [von](https://github.com/wfzyx/von)
  (ModernBERT-large, ~18 ms). **Not found:** any Jev, Laya or CLM evaluation on package-registry or supply-chain tasks.

## 2. Prior work: fine-tuned encoders vs LLM zero-shot, judges, distillation, routing

- [Bucher and Martini 2024](https://arxiv.org/abs/2406.08660): with 200 training examples, RoBERTa-large / DeBERTa-v3
  beat GPT-4 and Claude Opus zero-shot on all four tasks (stance 0.92 to 0.94 vs 0.58 to 0.61).
- [Wang 2024](https://arxiv.org/abs/2411.05050): BERT with 500 samples about 40% more accurate than any prompting.
- [BTZSC, ICLR 2026](https://arxiv.org/abs/2603.11991): 38 checkpoints; Qwen3-Reranker-8B macro-F1 0.72 vs
  instruction LLMs 0.67; embeddings best speed/accuracy trade-off.
- [Huang et al., ACL Findings 2025](https://arxiv.org/abs/2403.02839): a fine-tuned LLM judge "degenerates into a
  task-specific classifier"; DeBERTa classifiers match LLM judges in-domain.
- [Distillation to ModernBERT](https://arxiv.org/abs/2512.12677): Llama-3.2-3B teacher to ModernBERT-base student
  keeps 97% or more of teacher F1 at 45x throughput.
- Confidence-gated routing and escalation: [UCCI](https://arxiv.org/abs/2605.18796),
  [Signed Rescue Routing](https://arxiv.org/abs/2609.07786), [confidence-gated hybrid](https://arxiv.org/abs/2609.17977),
  [zero-shot confidence for small LLMs](https://arxiv.org/abs/2605.02241). *The mechanism is well studied; our
  contribution is the domain.*

## 3. ML in package-registry curation

- Typosquat: [ConfuGuard](https://arxiv.org/abs/2502.20528) (metadata plus classical ML, FP rate 80% to 28%, 630 real
  attacks, in production at Socket); [SpellBound 2020](https://arxiv.org/pdf/2003.03471);
  [Nesbitt 2025](https://nesbitt.io/2025/12/17/typosquatting-in-package-managers.html) and the
  [ecosyste.ms dataset](https://github.com/ecosyste-ms/typosquatting-dataset) (143 labelled squats);
  [Anvilogic CE-Typosquat-Detect](https://huggingface.co/Anvilogic/CE-Typosquat-Detect) (small encoder, domains).
- Malicious packages: [SocketAI, ICSE 2025](https://arxiv.org/abs/2403.12196) (GPT-4 99% precision, static pre-filter
  cuts LLM cost 76%; Socket runs LLM review in production); [Guo et al. 2026](https://arxiv.org/abs/2603.27549)
  (11 npm detectors, IntelGuard F1 95.98, GuardDog 93.32); [Samaana et al.](https://arxiv.org/abs/2412.05259)
  (ensemble F1 0.94 on PyPI); [13-LLM evaluation](https://arxiv.org/abs/2602.16304) (F1 0.40 to 0.99, triage only).
- License: [ScanCode](https://github.com/aboutcode-org/scancode-toolkit) (pattern plus probabilistic matching);
  [LiDetector](https://dl.acm.org/doi/10.1109/ASE56229.2023.00150); [PyPI license variants](https://arxiv.org/abs/2507.14594).
  **Not found:** a fine-tuned-encoder vs LLM head-to-head on license-family classification.
- Reachability: [VEX-Bench, EMNLP 2026](https://arxiv.org/abs/2609.08040) (75 expert cases, frontier LLMs ~80% F1);
  [Sifting the Noise, ISSTA 2026](https://arxiv.org/abs/2601.22952). Neither has a small-classifier baseline.
- Pattern: vendors use classical ML and heuristics for typosquat and metadata, LLMs for code review. **No one reports a
  fine-tuned encoder or decision model for curation triage.**

## 4. Jev architecture: claims vs evidence

- TypeSafe ([blog](https://typesafe.ai/blog/introducing-system-one-models-and-jev)): transformer, synthetic data, RLCD,
  "parallel" output, 255-option cap; size and base undisclosed. CEO on [HN](https://news.ycombinator.com/item?id=49717558):
  "close to the chest", data matters more than architecture.
- Hume (evidence-based): tokenizer nearest Qwen but not identical; MMLU-Pro 84.6% implies frontier pretraining, so a
  causal decoder is likely; an MoE guess is self-described as least certain; 32k/64k limits observed.
- Our own probes ([scripts/probe_jev.py](../scripts/probe_jev.py)): billed output tokens scale with option count and
  option-name length while latency stays flat; 20 questions per call cost the same as one; state length costs about
  8 ms per 1k tokens over a ~115 ms floor; no repeat-state cache. Consistent with single-pass joint scoring, not
  autoregressive generation.
- Unverified: a [note.com report](https://note.com/wayne_chang/n/n151303c2041a?hl=en) describing a "non-autoregressive
  encoder" repeats Laya's docs; a [KuCoin item](https://www.kucoin.com/news/flash/stanford-and-nvidia-open-source-clm-8b-9x-faster-than-jev-in-decision-making)
  labels CLM "Stanford and NVIDIA" (the repo lists authors only).

## 5. Open decoder-based Jev-likes and calibration-RL recipes with code

- Single-pass option scoring on decoders: [Kev](https://github.com/jaredpalmer/kev) (CE loss plus fitted temperature),
  [reflex](https://github.com/kshetrajna12/reflex) (Qwen3.5-4B), Open-Jev (Qwen3-4B), imajev and Standard One per
  [JevBench issues](https://github.com/fstandhartinger/jevbench/issues/80), [SALSA](https://arxiv.org/abs/2510.22691)
  (Llama-3.3-70B LoRA, class-token logits).
- Calibration RL with code: [RLCR](https://github.com/damanimehul/RLCR) (Brier reward, [arXiv 2507.16806](https://arxiv.org/abs/2507.16806)),
  [Rewarding Doubt](https://github.com/pasta99/RewardingDoubt) (log score, ICLR 2026); encoder-side: Laya's RLCD,
  [Verdict](https://github.com/Heman10x-NGU/Verdict-open-jev) (CE plus Brier, temperature scaling).

## What this means for the write-up

- **Novel:** first evaluation of any System One model on software supply-chain curation; first head-to-head of Jev vs
  fine-tuned Laya vs CLM vs Haiku on the same domain tasks; first report that CLM is at chance zero-shot on text
  classification (it was only ever evaluated on action scoring).
- **Already known, cite it:** small fine-tuned encoders beating frontier LLMs zero-shot (Bucher and Martini; Wang; BTZSC);
  in-domain specialists beating Jev (CUA-S1, Verdict, Laya's suite); Jev's ~0.1 raw ECE and the value of recalibration
  (hn-oracle, Beri); single-pass joint scoring and order sensitivity (Hume). Our 135 ms Jev latency is below the 236 to
  280 ms others measured; state where we measured from.
- **Temper:** JevBench shows Jev still leads open clones on generic tasks, so frame Laya's win as "with task fine-tuning".
  Beri's decomposition result suggests checking whether our reachability gap survives decomposing the question for Haiku.
  Hume's finding suggests an option-order-reversal check.
