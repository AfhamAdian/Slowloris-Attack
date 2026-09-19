# Sweep Summary

Attack-phase numbers for each attacker size N, from the baseline/attack/recovery experiment (Apache `MaxRequestWorkers=30`).

| N | Client success rate | Avg latency | Max busy workers | Max open conns |
|---|---|---|---|---|
| 20 | 100% | 0.05s | 12 (below the 30-worker pool — no denial) | 21 |
| 50 | 100% | 0.01s | 11 (below the 30-worker pool — no denial) | 20 |
| 100 | 100% | 0.01s | 11 (below the 30-worker pool — no denial) | 21 |
| 200 | 100% | 0.00s | 10 (below the 30-worker pool — no denial) | 18 |
