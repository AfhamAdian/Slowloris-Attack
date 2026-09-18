# Sweep Summary

Attack-phase numbers for each attacker size N, from the baseline/attack/recovery experiment (Apache `MaxRequestWorkers=30`).

| N | Attack success rate | Avg latency | Max busy workers | Max open conns |
|---|---|---|---|---|
| 20 | 100% | 0.09s | 23 (below the 30-worker pool — no denial) | 45 |
| 50 | 0% | 5.01s | pool exhausted | 150 |
| 100 | 0% | 5.01s | pool exhausted | 250 |
| 200 | 9% | 4.55s | pool exhausted | 450 |
