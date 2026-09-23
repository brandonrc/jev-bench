#!/usr/bin/env bash
# Separate network cost from inference: TCP connect + TLS handshake to each API host, 20 samples.
for host in api.typesafe.ai api.anthropic.com; do
  for i in $(seq 20); do curl -s -o /dev/null -w '%{time_connect} %{time_appconnect}\n' "https://$host/" ; done \
  | sort -n | awk -v h=$host '{c[NR]=$1;t[NR]=$2} END{printf "%-20s tcp p50=%.0fms  tls p50=%.0fms\n",h,c[int(NR/2)]*1000,t[int(NR/2)]*1000}'
done
