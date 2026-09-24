#!/usr/bin/env bash
# CLM heads on the corrected (raw prose) parquet: seed 1 already trained (runs/fair2-s1); train 2 and 3, evaluate
# each through clm-serve on the capped test splits, then cold latency in fresh processes. Run from jev-bench root.
set -u
CLM=/var/home/geraci/scratch/clm; V=../laya-smoke/.venv312/bin; CAP=768
stop_serve() { P=$(ss -ltnp 2>/dev/null | grep ":8700 " | grep -oE "pid=[0-9]+" | head -1 | cut -d= -f2); [ -n "$P" ] && kill $P; sleep 3; }
stop_vllm() { P=$(ss -ltnp 2>/dev/null | grep ":8090 " | grep -oE "pid=[0-9]+" | head -1 | cut -d= -f2); [ -n "$P" ] && kill $P; sleep 8; }
start_vllm() { (cd $CLM && CUDA_VISIBLE_DEVICES=1 nohup .venv/bin/vllm serve Qwen/Qwen3-8B --served-model-name qwen3-8b --runner pooling --enforce-eager --enable-prefix-caching --max-model-len 2048 --gpu-memory-utilization 0.85 --max-num-seqs 32 --port 8090 > logs/vllm-fix.log 2>&1 &); until curl -sf localhost:8090/v1/models >/dev/null; do sleep 5; done; }
serve() { (cd $CLM && CUDA_VISIBLE_DEVICES=0 CLM_CKPT=$CLM/checkpoints/CLM_v0.1-8B.pt nohup .venv/bin/clm-serve --port 8700 --emb-url http://127.0.0.1:8090/v1/embeddings --emb-model qwen3-8b --max-tokens 2048 --no-ui --action-cache 0 --model "clm-ft=$1" > logs/clm-serve-fix.log 2>&1 &); until curl -sf localhost:8700/v1/models >/dev/null; do sleep 2; done; }
curl -sf localhost:8090/v1/models >/dev/null || start_vllm
stop_serve
for seed in 1 2 3; do
  if [ ! -f $CLM/runs/fair2-s$seed/best_head.pt ]; then
    echo "=== CLM head fine-tune seed $seed (raw prose states) $(date +%H:%M)"
    (cd $CLM && .venv/bin/python train/finetune.py --task choice --data /var/home/geraci/scratch/jev-bench/data/clm-typed-$CAP --workflow all --init-ckpt checkpoints/CLM_v0.1-8B.pt --out-dir runs/fair2-s$seed --embed-url http://127.0.0.1:8090/v1/embeddings --served-model-name qwen3-8b --max-len 2048 --epochs 20 --seed $((1234+seed)) 2>&1 | grep -E "best epoch|Error|Traceback" | cut -c1-220)
  fi
  serve "$CLM/runs/fair2-s$seed/best_head.pt"
  echo "=== served eval seed $seed"
  $V/python -m jev_bench.run --engines "clm-http:http://localhost:8700#clm-ft" --tasks quarantine curation typosquat reachability license --split test --state-cap $CAP --concurrency 4 --out results/fair/raw-clm-tmp 2>&1 | grep -E "^(clm|Traceback|.*Error)"
  for f in results/fair/raw-clm-tmp/clm-ft__*.jsonl; do t=$(basename "$f" | sed "s/clm-ft__//"); sed "s/\"run\": 0/\"run\": $((seed-1))/" "$f" >> results/fair/raw/clm-ft__$t; done; rm -rf results/fair/raw-clm-tmp
  stop_serve
done
echo "=== fresh processes for cold latency"; stop_vllm; start_vllm; serve "$CLM/runs/fair2-s3/best_head.pt"
$V/python -m jev_bench.latency --engines "clm-http:http://localhost:8700#clm-ft" --n 40 --state-cap $CAP --out results/fair/latency.jsonl 2>&1 | grep -vE "Fetching|it/s\]"
stop_serve; stop_vllm; echo "=== CLM fixed run done $(date +%H:%M)"
