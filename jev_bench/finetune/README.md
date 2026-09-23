# Fine-tuning Laya on jev-bench tasks

Adapted from Laya's Kaggle notebook (`notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb`):
same RLCD loss (GRPO-style policy gradient over noisy logits with a strictly proper scoring reward,
plus soft cross-entropy), same post-training temperature refit on a held-out calibration slice.
Only the data loading and the checkpoint I/O are ours.

Training uses **train-split items only** (`jev_bench.tasks.split_of`, 80/20 by item id). Evaluate
fine-tuned checkpoints with `--split test`; anything else is leakage.

## Commands

```sh
VENV=../laya-smoke/.venv312/bin          # python 3.12 + torch 2.14 cu130 + laya

# 1. sequences (one-hot targets from Item.label)
$VENV/python -m jev_bench.finetune.prepare --run smoke-quarantine --tasks quarantine

#    distillation: soft targets from Jev's probabilities in results/distill/jev__<task>.jsonl
#    (produce them with: python -m jev_bench.run --engines jev --tasks ... --out results/distill)
$VENV/python -m jev_bench.finetune.prepare --run all-distill --tasks quarantine reachability license \
    --distill --distill-weight 1.0 --max-len 2048 --head-max-len 256

# 2. train on both 3090s
NCCL_P2P_DISABLE=1 PYTHONUNBUFFERED=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
$VENV/torchrun --standalone --nproc_per_node=2 -m jev_bench.finetune.train_ddp --run smoke-quarantine --epochs 4

# 3. evaluate on the TEST split with the normal runner
$VENV/python -m jev_bench.run --engines laya:$PWD/data/checkpoints/smoke-quarantine/model@cuda:0 \
    --tasks quarantine --split test --out results/raw-ft
```

## Flags that matter

- `--max-len` / `--head-max-len` (prepare and train): Laya's limit is `rl_agent_config.json`
  (512/192 base, 1024/256 typed-decisions), not the encoder; ModernBERT-large takes up to 8192
  positions. Both scripts override the config and the value is written into the output checkpoint,
  so `laya.load()` uses it at inference. Memory: token-budget batching
  (`--max-tokens-per-batch`, default 16384 padded tokens per GPU) keeps long runs inside 24 GB.
- `--state-chars` (prepare, default 4000) caps the serialized state; reachability states are also
  pruned to the paths that reach the finding's package (`compact.py`). The same compaction is
  applied at inference by `engines/laya.py` for any checkpoint whose config carries `jev_bench`.
- `--distill` / `--distill-weight`: soft targets from Jev, mixed with one-hot at `w`.

## Output layout (what laya.load expects)

```
data/checkpoints/<run>/model/
  model.safetensors        fp16
  rl_agent_config.json     max_len/head_max_len, fitted temperature[3], jev_bench{...}, training{...}
  encoder/config.json
  tokenizer/
```

## Gotchas

- ModernBERT's `reference_compile` auto-enables `torch.compile` on CUDA; with variable-length batches
  it recompiles per shape and the smoke run sat at 100% GPU for 10+ minutes without finishing an
  epoch. `train_ddp.py` forces it off (laya's Agent does the same at inference).
- Python 3.14 has no headers on Bazzite, so Triton cannot build; use the uv-managed 3.12 venv.
- `NCCL_P2P_DISABLE=1` for consumer GPUs; DDP over two 3090s otherwise works with `--standalone`.
- Don't skip the calibration refit: `temperature_by_options` from the base checkpoint is dropped and
  a per-type temperature is fitted on the calib slice, otherwise confidences are meaningless.
