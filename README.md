# Slowloris-Attack

Slowloris DoS demonstration. See `slowloris-project-design.md` for the full
project design. This covers the undefended-server phase: setting up the
vulnerable Apache target, running the attack, and producing the result
graphs, including a sweep across attacker sizes N = 20, 50, 100, 200.

## Layout

- `core/` — the three building-block scripts (attacker, legitimate client,
  monitor). Each can be run standalone.
- `experiments/` — orchestration: runs one experiment end to end, plots it,
  and runs the N sweep.
- `scripts/` — one-off setup (Apache install/config).
- `results/` — everything an experiment produces (gitignored-worthy, but
  kept here for the report). Per run: graphs directly under the run's
  directory, raw CSV/JSON/stdout logs nested under a `logs/` subdirectory.

## 1. Set up the target server

```
bash scripts/setup_apache.sh
```

Installs Apache, switches it to the prefork MPM, caps the worker pool at
`MaxRequestWorkers=30`, enables `mod_status` at `/server-status`, and makes
sure `mod_reqtimeout` is disabled (no defense yet). Needs sudo.

## 2. Install Python dependencies

```
pip install -r requirements.txt
```

## 3. Core scripts (`core/`)

- `attacker.py` — opens `--num-sockets` connections and trickles one header
  line at a time on each, every `--interval` seconds, never completing the
  request.
- `legitimate_client.py` — sends one normal request every `--rate` seconds
  and logs success/failure + latency to a CSV.
- `monitor.py` — polls Apache's `/server-status?auto` and `ss -tn` every
  `--poll-interval` seconds and logs worker count, connection count, CPU%,
  and memory% to a CSV.

Each can be run standalone (`python3 core/attacker.py --help` etc.), but
normally you don't need to — the orchestration scripts below drive them.

## 4. Run one experiment (`experiments/`)

```
python3 experiments/run_experiment.py --n 100 --out-dir results/single_run
python3 experiments/plot_results.py --dir results/single_run
```

`run_experiment.py` starts the monitor and legitimate client, runs a
baseline period, then starts the attacker with `N` connections for the
attack period, then lets everything run through a recovery period and
stops. Raw CSV/JSON/stdout logs are saved under `results/single_run/logs/`.
`plot_results.py` reads that directory and produces, directly under
`results/single_run/`:

- `1_worker_saturation.png` — busy workers & open connections vs time
- `2_cpu_mem.png` — CPU/memory vs time (stays flat: not volumetric)
- `3_client_success_rate.png` — legitimate client success rate vs time
- `4_client_latency.png` — legitimate client response time vs time

and `results/single_run/logs/summary.txt` / `summary.json` — per-phase
numbers (success rate, avg latency, max busy workers, max open connections,
time to saturation).

## 5. Run the full sweep (N = 20, 50, 100, 200)

```
python3 experiments/run_sweep.py
```

Runs the experiment above once per N into `results/sweep_N20/`,
`results/sweep_N50/`, `results/sweep_N100/`, `results/sweep_N200/` (each
with its own 4 graphs at the top level and raw logs/summary under its own
`logs/` subdirectory), then also produces, directly under `results/`:

- `sweep_comparison.png` — time-to-saturation and attack-phase success
  rate, both plotted against N
- `sweep_comparison.csv` — the same numbers as a table

Runs are sequential (they share one Apache server), so the whole sweep
takes roughly `4 x (baseline + attack + recovery)` seconds — a few minutes
with the defaults. Adjust timing with `--baseline-secs`, `--attack-secs`,
`--recovery-secs` on either `run_experiment.py` or `run_sweep.py`.
