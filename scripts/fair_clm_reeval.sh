#!/usr/bin/env bash
# Re-evaluate the three fine-tuned CLM heads with the server tokenizing like training (CLM_SEND_IDS=1),
# after checking that string-vs-ids embeddings really differ. Overwrites results/fair/raw/clm-ft__* (old rows kept
# under results/fair/ablations/clm-ft-text-tokenized/). Run from the jev-bench root once the GPUs are free.
set -u
CLM=../clm; V=../laya-smoke/.venv312/bin; CAP=${CAP:-768}
(cd $CLM && CUDA_VISIBLE_DEVICES=1 nohup .venv/bin/vllm serve Qwen/Qwen3-8B --served-model-name qwen3-8b --runner pooling --enforce-eager --enable-prefix-caching --max-model-len 2048 --gpu-memory-utilization 0.85 --max-num-seqs 32 --port 8090 > logs/vllm-reeval.log 2>&1 &)
until curl -sf localhost:8090/v1/models >/dev/null; do sleep 5; done; echo "vllm up"
echo "=== A/B: same text embedded as string vs as training-style ids"
(cd $CLM && PYTHONPATH=src:train .venv/bin/python - <<'PY'
import numpy as np, sys; sys.path.insert(0, "train"); import embed_utils
from clm.embedder import Embedder
import os
texts = ["artifact: lodash@4.17.21\nevents: ClamAV: Win.Trojan.Agent FOUND\n\nWhy was this artifact quarantined?", "install scripts fetch remote code, credential theft, obfuscation"]
e_text = Embedder(); os.environ["CLM_SEND_IDS"] = "0"; a, _ = e_text.embed(texts)
os.environ["CLM_SEND_IDS"] = "1"; e_ids = Embedder(); b, _ = e_ids.embed(texts)
rec = embed_utils.Recipe("Qwen/Qwen3-8B", 2048); back = embed_utils.ServerBackend("http://127.0.0.1:8090/v1/embeddings", "qwen3-8b")
c = back.embed([rec.text_ids(t, keep="tail") for t in texts])
for i, t in enumerate(texts): print(f"cos(text, ids)={float(a[i]@b[i]):.4f}  cos(ids, training-recipe)={float(b[i]@c[i]):.4f}  cos(text, training-recipe)={float(a[i]@c[i]):.4f}")
PY
)
mkdir -p results/fair/ablations/clm-ft-text-tokenized && mv results/fair/raw/clm-ft__*.jsonl results/fair/ablations/clm-ft-text-tokenized/ 2>/dev/null
serve() { (cd $CLM && CLM_SEND_IDS=1 CUDA_VISIBLE_DEVICES=0 CLM_CKPT=$PWD/checkpoints/CLM_v0.1-8B.pt nohup .venv/bin/clm-serve --port 8700 --emb-url http://127.0.0.1:8090/v1/embeddings --emb-model qwen3-8b --max-tokens 2048 --no-ui --action-cache 0 $1 > logs/clm-serve-reeval.log 2>&1 &); until curl -sf localhost:8700/v1/models >/dev/null; do sleep 2; done; }
stop_serve() { P=$(ss -ltnp 2>/dev/null | grep ":8700 " | grep -oE "pid=[0-9]+" | head -1 | cut -d= -f2); [ -n "$P" ] && kill $P; sleep 3; }
for seed in 1 2 3; do
  serve "--model clm-ft=$CLM/runs/fair-s$seed/best_head.pt"
  echo "=== clm-ft seed $seed, ids-tokenized"
  $V/python -m jev_bench.run --engines "clm-http:http://localhost:8700#clm-ft" --tasks quarantine curation typosquat reachability license --split test --state-cap $CAP --concurrency 4 --out results/fair/raw-clm-tmp 2>&1 | grep -E "^(clm|Traceback|.*Error)"
  for f in results/fair/raw-clm-tmp/clm-ft__*.jsonl; do t=$(basename $f | sed "s/clm-ft__//"); sed "s/\"run\": 0/\"run\": $((seed-1))/" $f >> results/fair/raw/clm-ft__$t; done; rm -rf results/fair/raw-clm-tmp
  [ $seed -lt 3 ] && stop_serve
done
echo "=== zero-shot reference head, ids-tokenized (for the table)"; mkdir -p results/fair/ablations/clm-8b-text-tokenized && mv results/fair/raw/clm-8b__*.jsonl results/fair/ablations/clm-8b-text-tokenized/
$V/python -m jev_bench.run --engines clm-http:http://localhost:8700 --tasks quarantine curation typosquat reachability license --split test --state-cap $CAP --concurrency 4 --out results/fair/raw 2>&1 | grep -E "^(clm|Traceback|.*Error)"
echo "=== CLM latency protocol (cold, ids-tokenized)"; $V/python -m jev_bench.latency --engines clm-http:http://localhost:8700 "clm-http:http://localhost:8700#clm-ft" --n 40 --state-cap $CAP --out results/fair/latency.jsonl
stop_serve; P=$(ss -ltnp 2>/dev/null | grep ":8090 " | grep -oE "pid=[0-9]+" | head -1 | cut -d= -f2); [ -n "$P" ] && kill $P; echo "=== reeval done"
