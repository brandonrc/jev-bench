#!/usr/bin/env bash
# CLM leg of the fair comparison: vLLM encoder on GPU 1, clm-serve on GPU 0, zero-shot on capped test splits,
# three head fine-tunes on the capped train parquet, each evaluated the same way. Run from the jev-bench root.
set -u
CLM=../clm; V=../laya-smoke/.venv312/bin; CAP=${CAP:-768}
mkdir -p $CLM/logs results/fair/raw
(cd $CLM && CUDA_VISIBLE_DEVICES=1 nohup .venv/bin/vllm serve Qwen/Qwen3-8B --served-model-name qwen3-8b --runner pooling --enforce-eager --enable-prefix-caching --max-model-len 2048 --gpu-memory-utilization 0.85 --max-num-seqs 32 --port 8090 > logs/vllm-fair.log 2>&1 &)
until curl -sf localhost:8090/v1/models >/dev/null; do sleep 5; done; echo "vllm up"
serve() { # $1 = extra --model args
  (cd $CLM && CUDA_VISIBLE_DEVICES=0 CLM_CKPT=$PWD/checkpoints/CLM_v0.1-8B.pt nohup .venv/bin/clm-serve --port 8700 --emb-url http://127.0.0.1:8090/v1/embeddings --emb-model qwen3-8b --max-tokens 2048 --no-ui --action-cache 0 $1 > logs/clm-serve-fair.log 2>&1 &)
  until curl -sf localhost:8700/v1/models >/dev/null; do sleep 2; done; }
stop_serve() { P=$(ss -ltnp 2>/dev/null | grep ":8700 " | grep -oE "pid=[0-9]+" | head -1 | cut -d= -f2); [ -n "$P" ] && kill $P; sleep 3; }
serve ""
echo "=== CLM zero-shot, capped test splits"
$V/python -m jev_bench.run --engines clm-http:http://localhost:8700 --tasks quarantine curation typosquat reachability license --split test --state-cap $CAP --concurrency 4 --out results/fair/raw 2>&1 | grep -E "^(clm|Traceback|.*Error)"
stop_serve
for seed in 1 2 3; do
  echo "=== CLM head fine-tune seed $seed"
  (cd $CLM && .venv/bin/python train/finetune.py --task choice --data /var/home/geraci/scratch/jev-bench/data/clm-typed-$CAP --workflow all --init-ckpt checkpoints/CLM_v0.1-8B.pt --out-dir runs/fair-s$seed --embed-url http://127.0.0.1:8090/v1/embeddings --served-model-name qwen3-8b --max-len 2048 --epochs 20 --seed $((1234+seed)) 2>&1 | grep -E "best epoch|\[done\]|Error|Traceback")
  serve "--model clm-ft=$CLM/runs/fair-s$seed/best_head.pt"
  $V/python -m jev_bench.run --engines "clm-http:http://localhost:8700#clm-ft" --tasks quarantine curation typosquat reachability license --split test --state-cap $CAP --concurrency 4 --out results/fair/raw-clm-tmp 2>&1 | grep -E "^(clm|Traceback|.*Error)"
  for f in results/fair/raw-clm-tmp/clm-ft__*.jsonl; do t=$(basename $f | sed "s/clm-ft__//"); sed "s/\"run\": 0/\"run\": $((seed-1))/" $f >> results/fair/raw/clm-ft__$t; done; rm -rf results/fair/raw-clm-tmp
  [ $seed -lt 3 ] && stop_serve
done
echo "=== CLM latency protocol (fresh server, cold, seed-3 head)"
$V/python -m jev_bench.latency --engines clm-http:http://localhost:8700 "clm-http:http://localhost:8700#clm-ft" --n 40 --state-cap $CAP --out results/fair/latency.jsonl
stop_serve; P=$(ss -ltnp 2>/dev/null | grep ":8090 " | grep -oE "pid=[0-9]+" | head -1 | cut -d= -f2); [ -n "$P" ] && kill $P
echo "=== CLM leg done"
