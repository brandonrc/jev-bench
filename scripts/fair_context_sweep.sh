#!/usr/bin/env bash
# Context as its own dimension: accuracy on license + reachability test splits vs state cap, for the
# fine-tuned Laya (seed 1, retrained per cap so train and test see the same budget) and the tuned CLM head
# (seed 1 head, cap applied at inference only since its encoder window is fixed). Run from jev-bench root.
set -u
V=../laya-smoke/.venv312/bin; export NCCL_P2P_DISABLE=1 PYTHONUNBUFFERED=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
mkdir -p results/fair/context
for cap in 256 512 768 1536 2048; do
  run=ctx-laya-$cap; ml=$(( cap + 256 )); [ $ml -lt 512 ] && ml=512
  echo "=== laya cap $cap (max_len $ml)"
  $V/python -m jev_bench.finetune.prepare --run $run --tasks license reachability quarantine curation typosquat --state-cap $cap --max-len $ml --head-max-len 256 --seed 20260923 2>&1 | grep -E "wrote"
  $V/torchrun --standalone --nproc_per_node=2 -m jev_bench.finetune.train_ddp --run $run --epochs 4 2>&1 | grep -E "^=== epoch 4|calibration|Error|Traceback"
  $V/python -m jev_bench.run --engines laya:$PWD/data/checkpoints/$run/model@cuda:0 --tasks license reachability --split test --state-cap $cap --out results/fair/context/laya-$cap 2>&1 | grep -E "^(laya|Traceback|.*Error)"
done
echo "=== context sweep (laya) done"
