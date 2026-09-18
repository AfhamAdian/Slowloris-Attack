# How to Run / Test

Step-by-step instructions to reproduce the Slowloris demonstration from a
clean checkout: set up the vulnerable Apache target, run the attack, and
produce the result graphs (including the N sweep). See
`slowloris-project-design.md` for the background/theory and `README.md`
for a shorter overview of the layout.

This covers the **undefended** server only — no live-demo or
`mod_reqtimeout` defense steps here.

## 0. Prerequisites

- Linux with `sudo` access (Apache install/config needs it).
- Python 3.9+.
- Nothing should already be listening on port 80.

## 1. Set up the target server

```
bash scripts/setup_apache.sh
```

This will prompt for your sudo password. It:
1. Installs Apache.
2. Switches it to the **prefork** MPM (one worker process per connection —
   the model this attack exploits).
3. Caps the worker pool: `MaxRequestWorkers 30` (small on purpose, so
   exhaustion happens in seconds instead of needing thousands of
   connections).
4. Enables `mod_status` at `http://127.0.0.1/server-status`.
5. Explicitly disables `mod_reqtimeout` — this is the undefended baseline.
6. Restarts Apache and prints its status plus a `server-status?auto` check.

**Verify it worked:**

```
curl -s "http://127.0.0.1/server-status?auto"
```

You should see `ServerMPM: prefork` and lines like `BusyWorkers: 1`,
`IdleWorkers: 9`.

## 2. Install Python dependencies

```
pip install -r requirements.txt
```

Installs `psutil` (CPU/memory stats), `pandas` and `matplotlib` (plotting).

## 3. Sanity-check the core scripts (optional)

Each script in `core/` also runs standalone if you want to watch it by
hand before automating everything:

```
python3 core/monitor.py --duration 5
python3 core/legitimate_client.py --duration 5
python3 core/attacker.py --num-sockets 10 --duration 5
```

Ctrl+C stops any of them early. Run `python3 core/<script>.py --help` for
the full list of options (target IP/port, rate, interval, etc).

## 4. Run one full experiment

```
python3 experiments/run_experiment.py --n 100 --out-dir results/single_run
python3 experiments/plot_results.py --dir results/single_run
```

`run_experiment.py` automates the whole baseline → attack → recovery
sequence for one attacker size `N`:
1. Starts the monitor and legitimate client (they run for the whole
   experiment).
2. Waits `--baseline-secs` (default 20s) with no attacker running.
3. Starts the attacker with `N` connections for `--attack-secs` (default
   60s), then it exits on its own.
4. Keeps the monitor/client running for `--recovery-secs` (default 30s)
   after the attacker stops, then everything exits.

Output layout:

```
results/single_run/
  1_worker_saturation.png
  2_cpu_mem.png
  3_client_success_rate.png
  4_client_latency.png
  logs/
    monitor_log.csv
    client_log.csv
    phases.json
    summary.txt
    summary.json
    attacker_stdout.log
    monitor_stdout.log
    client_stdout.log
```

**What to check in `logs/summary.txt`:**
- `[baseline]` and `[recovery]` should both show `success=100.0%` and
  low `avg_latency`.
- `[attack]` should show `success` collapsed toward 0% and `avg_latency`
  near your client's timeout (default 5s).
- `avg_cpu` should stay low in all three phases — proof this is a
  connection-exhaustion attack, not a volumetric one.

## 5. Run the full sweep (N = 20, 50, 100, 200)

```
python3 experiments/run_sweep.py
```

Runs step 4 once per N into its own directory (same layout as above, plus
its own `logs/` subfolder):

```
results/sweep_N20/...
results/sweep_N50/...
results/sweep_N100/...
results/sweep_N200/...
results/sweep_comparison.png
results/sweep_comparison.csv
```

`sweep_comparison.png`/`.csv` compare all four runs side by side:
time-to-saturation vs N, and attack-phase client success rate vs N.

Runs are sequential (they share the one Apache server), so the whole
sweep takes roughly `4 x (baseline + attack + recovery)` seconds — a few
minutes with the defaults. To customize:

```
python3 experiments/run_sweep.py --ns 20 50 100 200 \
  --baseline-secs 20 --attack-secs 60 --recovery-secs 30
```

**Expected result** (with `MaxRequestWorkers=30`): N=20 stays under the
pool size, so the legitimate client should see ~100% success throughout —
no denial of service. N=50, 100, and 200 should all fully saturate the
pool and drop the client to ~0% success during the attack window. That
contrast is the main thing the sweep is meant to show.

## 6. Between runs / troubleshooting

- **Apache stuck / port 80 still busy after a run**: `sudo systemctl
  restart apache2` clears any stuck connections before the next run.
- **`results/single_run` or `results/sweep_N*` already exists**: the
  scripts overwrite files in place, so it's safe to re-run without
  deleting first — but delete old runs if you want a clean directory
  listing for the report.
- **Confirm the server really is prefork with the small pool**:
  ```
  curl -s "http://127.0.0.1/server-status?auto" | grep -E "ServerMPM|BusyWorkers|IdleWorkers"
  ```
- **Connection-count metric looks too high**: `monitor.py` counts open
  TCP connections with `ss -tn` filtered to the exact target port. If you
  change `--target-port`, make sure nothing else on the machine is using
  that same port, or the count will include unrelated connections.
