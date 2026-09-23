| task | engine | n | acc | lenient | macro-F1 | ECE | cov@0.9 | acc@0.9 | p50 ms | p95 ms | p99 ms | items/s | c |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| license | claude-haiku-4-5 | 807 | 0.646 | 0.773 | 0.649 | 0.192 | 0.42 | 0.871 | 900 | 1347 | 1767 | 8.2 | 8 |
| license | jev | 807 | 0.644 | 0.777 | 0.662 | 0.139 | 0.48 | 0.841 | 185 | 265 | 337 | 20.7 | 4 |
| license | laya-base | 807 | 0.271 | 0.428 | 0.221 | 0.145 | 0.00 | 1.000 | 20 | 26 | 28 | 48.3 | 1 |
| license | laya-typed-decisions | 807 | 0.206 | 0.315 | 0.167 | 0.117 | 0.00 | nan | 24 | 38 | 41 | 35.8 | 1 |
| quarantine | claude-haiku-4-5 | 420 | 0.974 | - | 0.974 | 0.030 | 0.99 | 0.981 | 817 | 1298 | 2531 | 8.4 | 8 |
| quarantine | jev | 420 | 1.000 | - | 1.000 | 0.012 | 0.95 | 1.000 | 171 | 247 | 306 | 22.3 | 4 |
| quarantine | laya-base | 420 | 0.740 | - | 0.752 | 0.417 | 0.00 | 1.000 | 18 | 19 | 19 | 55.4 | 1 |
| quarantine | laya-typed-decisions | 420 | 0.748 | - | 0.736 | 0.672 | 0.00 | nan | 19 | 24 | 25 | 46.7 | 1 |
| reachability | claude-haiku-4-5 | 450 | 0.620 | - | 0.605 | 0.343 | 0.97 | 0.612 | 959 | 1448 | 2118 | 7.6 | 8 |
| reachability | jev | 450 | 0.889 | - | 0.883 | 0.045 | 0.86 | 0.906 | 187 | 250 | 325 | 20.8 | 4 |
| reachability | laya-base | 450 | 0.449 | - | 0.317 | 0.259 | 0.00 | nan | 20 | 21 | 22 | 49.4 | 1 |
| reachability | laya-typed-decisions | 450 | 0.444 | - | 0.308 | 0.202 | 0.00 | nan | 32 | 34 | 35 | 31.8 | 1 |

## Slices (accuracy by meta field)

- **license / claude-haiku-4-5**: variant=rebranded 0.648, variant=truncated 0.595, variant=verbatim 0.678
- **license / jev**: variant=rebranded 0.641, variant=truncated 0.577, variant=verbatim 0.695
- **license / laya-base**: variant=rebranded 0.27, variant=truncated 0.27, variant=verbatim 0.273
- **license / laya-typed-decisions**: variant=rebranded 0.189, variant=truncated 0.205, variant=verbatim 0.222
- **quarantine / claude-haiku-4-5**: hard=False 0.97, hard=True 0.988
- **quarantine / jev**: hard=False 1, hard=True 1
- **quarantine / laya-base**: hard=False 0.765, hard=True 0.643
- **quarantine / laya-typed-decisions**: hard=False 0.771, hard=True 0.655
- **reachability / claude-haiku-4-5**: scenario=a 1, scenario=b 1, scenario=c 0.48, scenario=d 0.16, scenario=e 0.18, scenario=f 0.24, scenario=g 0.86, scenario=h 0.88, scenario=i 0.78
- **reachability / jev**: scenario=a 1, scenario=b 1, scenario=c 1, scenario=d 1, scenario=e 1, scenario=f 1, scenario=g 1, scenario=h 1, scenario=i 0
- **reachability / laya-base**: scenario=a 1, scenario=b 1, scenario=c 0, scenario=d 0, scenario=e 0.02, scenario=f 0, scenario=g 0.02, scenario=h 1, scenario=i 1
- **reachability / laya-typed-decisions**: scenario=a 1, scenario=b 1, scenario=c 0, scenario=d 0, scenario=e 0, scenario=f 0, scenario=g 0, scenario=h 1, scenario=i 1
