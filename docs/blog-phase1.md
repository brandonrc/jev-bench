# I benchmarked the new "decision models" on my package curation problem. The small one you can train yourself won.

*Phase 1 draft. Square brackets are slots for you. No numbers in this post are made up; every one is in
github.com/brandonrc/jev-bench under results/fair.*

## Why I cared

I've been building artifact-keeper, [one line on what it is and who it's for]. It sits in front of package
registries and decides what gets in. Most of that is deterministic: allow, block, or push to a review queue. The
review queue is the problem. It's human labor, and it fills up with stuff that a person has to look at one at a
time. [How big does the pile get? Who looks at it? What does a bad day look like?]

The questions in that pile are boring in a good way. Is this package a typosquat of something popular, or an
honest fork with a similar name? What license family is this LICENSE file that doesn't match any SPDX id? Does
this scanner finding actually reach anything in the declared dependency graph, or is it noise? Why did this
artifact get quarantined? None of those need an essay. They need a label and a number for how sure you are, so
the queue can sort itself and a person only looks at the uncertain ones. Get it wrong and someone reviews things
in a slightly worse order. Nobody gets breached.

[Your own words on what you already had: the typosquat detector in typosquat.rs does Damerau-Levenshtein, UTS #39
confusable skeletons and affix detection, and the affix part had to be popularity-gated because it false-positives
on legit names. That's the itch. The lexical layer can't see that lodash-es is fine and lodahs is not.]

So when TypeSafe shipped Jev in September and called it a "System One model", a thing that answers typed
questions with calibrated probabilities instead of writing text, I wanted to know if it was real. Then two open
ones showed up the same week, Laya and CLM-8B, and Claude Haiku exists, so I built a benchmark.

## What I tested

Five tasks, all shaped like the review pile, 5,561 items, all from public data or built from it:

| Task | Question type | Data |
|---|---|---|
| Quarantine reason | pick one of 7 | templates modeled on ClamAV, Trivy, Grype, ScanCode, OPA and cosign output |
| Curation review | malicious, abandoned, license-incompatible, benign | real npm and PyPI metadata; the malicious rows are 300 real OSV advisories |
| Typosquat second stage | yes or no | 600 malicious names from OSV vs 615 real packages with similar names |
| Finding reachability | yes or no | real OSV advisories planted into dependency trees, ground truth by walking the graph in code |
| License family | pick one of 8 | 2,271 real license texts from ScanCode, verbatim, rebranded and truncated |

Seven columns: Jev, Claude Haiku 4.5 as the "what if I just used an LLM" baseline, Laya off the shelf, Laya after
I fine-tuned it, CLM-8B off the shelf, and CLM after fine-tuning its head.

## The rules, because the rules decided it

The first pass was a mess of accidental differences. Laya reads 1k tokens, CLM 2k, Jev 32k. CLM caches embeddings
so a repeated input answers in 1 ms. The fine-tuned models saw different renderings of the input than the hosted
ones. A friend looked at it and said cap the context for everyone and treat context as its own experiment. He was
right. So:

1. Every model gets the exact same bytes: the state rendered to plain `key: value` text and cut at 768 tokens,
   with 256 left for the question, so it fits a 1k budget even the smallest model can read whole.
2. Every number is on a held-out test split, 20% of each task by a hash of the item id. The fine-tunes never see it.
3. Both fine-tunes train on the same labels, three random seeds each, and I report the spread.
4. Latency is one request at a time, cold cache, fresh server process, from my desk. The hosted ones include my
   home internet, which is part of the deal.
5. Context is a separate sweep afterwards, not a confound.
6. Where the data leaks, I say so. The typosquat positives have templated README and publisher fields because the
   real packages are gone from the registries, and a fine-tuned model learns the template. Those cells are marked
   and not in any headline.

## What I got

[table from docs/_fair_table.md goes here once the CLM rerun lands]

Some things I didn't expect.

**Off the shelf, the open models were at chance.** Laya scored 31% on curation and 23% on license with no
training. CLM was worse. Jev, with no training either, scored 94% and 63% on the same items. That gap is the
product TypeSafe is selling: a model that reads a rubric you wrote five minutes ago and mostly gets it right.

**Eighteen minutes of training flipped it.** Laya fine-tuned on the train split, three times over with different
seeds, on the two 3090s in my office: 99.6% on quarantine, 98% on curation, 84% on reachability, 78% on license.
Jev was 100, 94, 89, 63. So a 421M model I own matched or beat the hosted one on every honest task, at 21
milliseconds against 135. On license it wasn't close, because it learned the weird corners of ScanCode's taxonomy
from the labels and no rubric can teach a hosted model that.

**Rubric wording was worth 15 points on Jev.** My first curation rubric said "no release in years" for abandoned.
Jev called 204 of 300 abandoned packages benign. I changed it to "last release more than 4 years ago, even if not
flagged" and it went from 80% to 95% on the same items. Haiku inferred the rule either way. That's the whole
Jev workflow in one example: the lever is the sentence, and it's a strong lever.

**Jev has a blind spot I could reproduce fifty times.** Reachability has a scenario where the vulnerable package
sits under both a dev path and a prod path. Jev got 0 of 50. It saw "dev" and stopped. Every other scenario it
got right. A model that reads once and answers can't combine two facts, and their docs say as much.

**Haiku is accurate and slow.** It tied Jev on three tasks, beat it slightly on curation, and lost badly on
reachability at 59%, confidently calling dev-only findings reachable. A second per decision, 8x Jev and 50x
Laya, and about 25x Jev's cost per token.

**CLM is built for a different problem.** It embeds each answer option separately and picks the nearest, which
is great when the same screen gets scored against fifty possible actions, and useless for "which of these seven
quarantine reasons". [Fixed CLM tuned numbers here.] I also cost myself half a day on it: my export stored the
input as a JSON-quoted string, its loader kept that as literal text, and the model trained on `"...\n..."` while
the server saw real newlines. Same text, same numbers. Worth writing down because everyone will hit a version of
that.

## Poking at Jev from the outside

I couldn't leave the black box alone, so I ran a few hundred controlled calls against it.

- Billed output tokens grow by about 9 per answer option. 64 options billed 584 tokens. Latency didn't move.
  A model actually writing 584 tokens would take seconds. So the "output" is an accounting of the answer's size,
  not generation.
- Twenty questions in one call cost the same as one. It scores them in parallel.
- Reading cost is real but small: about 8 ms per thousand tokens on top of a 115 ms floor, 70 of which is my
  round trip. It read 16,000 tokens in a quarter second.
- Sending the identical input twenty times: no speedup. No cache.
- Reversing the option order flipped 0 of 60 quarantine answers, 2 of 60 curation, 4 of 60 license.

Put together: Jev reads the whole form once and scores every option in that pass. It is not writing its answer
word by word, and it is not CLM's cached-embedding design. In behavior it's Laya's design with a much stronger
reader on much faster hardware. What it's made of, nobody outside TypeSafe knows, and I'd keep it that way in
your head too: consistent with, not is.

## What everyone else found

Jev is a week old and there are already eight or so independent evals. Short version. On generic LLM-written
decision tasks, Jev leads every open clone on the public leaderboard, Laya included, so my Laya result is a
fine-tuned result on my tasks and nothing more. Tiny in-domain specialists beating Jev is a pattern other people
hit too, and the academic version is from 2024. One phishing study found Haiku beats Jev on a single holistic
question and Jev beats Haiku once you split it into atomic questions, which matches what I saw. Jev's raw
calibration is about 0.1 off across studies and fixes with a post-hoc recalibration. Nobody has tried any of this
on package curation. Links in the repo.

## What I didn't test

- My own queue. Everything here is public or synthetic, and two of the five tasks are synthetic enough that a
  fine-tune can learn the template. The next step is an export of real review decisions through the same harness.
- Load. One stream on a quiet box. Jev scaled to 150 decisions a second at 64 streams from one test key, but a
  real soak test with p99s is separate work.
- CPU. Laya on a Ryzen 5900X was 270 to 710 ms per item, 15 to 25x the GPU. I didn't try ONNX.
- Adversarial READMEs. They're attacker-controlled and none of the open models have any defense.
- Non-English packages, and drift.

## Where this leaves me

The two-stage answer is the honest one. A rule-driven model like Jev is for questions you haven't asked yet:
bootstrapping labels when you have none, the long tail of fifty small questions a pipeline asks a few hundred
times a month, and things an agent decides to ask at runtime. A fine-tuned small model is for the questions you
ask all day, once you have labels, and in my pipeline that's nearly all the volume. Code is for anything that's
actually logic, like walking a dependency graph. I pruned the tree in twenty lines and it beat every context
setting.

Phase 2 is the obvious experiment: a Qwen-class open model, a few billion parameters, trained the way Laya trains
but with a reader that handles 32k tokens and reads structure properly, on my own forms. I think it lands between
fine-tuned Laya and Jev on accuracy, near Jev on speed, and wins on the long tail because it reads like a
language model. I'll find out.

No open model matches Jev as a general-purpose decision engine today. For my pipeline, that turned out not to be
the question.

[Sign-off in your words. Repo link. Anything you want people to try.]
