# How to Run / Test — Defended Server

Step-by-step instructions to reproduce the **defended** Slowloris run:
same Apache install, same attack scripts, but with the two defenses from
Section 11 of `slowloris-project-design.md` turned on:

1. **Header timeout cap** (`mod_reqtimeout`) — bounds how long Apache will
   wait for the request headers, no matter how well-timed the attacker's
   sends are.
2. **Per-source-IP concurrent connection limit** (`iptables` connlimit) —
   caps how many connections one IP may hold open on port 80 at once.

This assumes you've already done the undefended run (`run-test.md`). If
not, do that first — you'll want both result sets to compare against each
other in the report.

## 0. Why there's an extra IP involved

The attacker and the legitimate client both run on this same machine and
normally both connect from `127.0.0.1` — same source IP. A per-IP
connection limit can't tell them apart if that's left as is, and would
throttle the legitimate client too.

The fix: the attacker binds its outgoing sockets to a second loopback
alias, `127.0.0.2`, instead of the default. Linux treats all of
`127.0.0.0/8` as loopback with no extra setup needed — this is already
built into `core/attacker.py` via `--source-ip` and wired through
`run_experiment.py`/`run_sweep.py` via `--attacker-source-ip`. The
connlimit rule targets `127.0.0.2` specifically, so the legitimate client
(still on `127.0.0.1`) is never touched by it.

## 1. Enable the defense

```
bash scripts/enable_defense.sh
```

Prompts for your sudo password. It:
1. Writes `/etc/apache2/mods-available/reqtimeout.conf` with
   `RequestReadTimeout header=10-20,MinRate=500` (+ a body timeout) and
   enables `mod_reqtimeout`.
2. Adds an `iptables` rule: connections from `127.0.0.2` to port 80 above
   10 concurrent are rejected.
3. Restarts Apache.
4. Prints both checks (`apache2ctl -M | grep reqtimeout`, the iptables
   rule listing) so you can confirm they took effect before moving on.

**Everything else about the server is unchanged** — same prefork MPM,
same `MaxRequestWorkers=30`, same `mod_status`. Only the two defenses are
new, so any difference in results is attributable to them.

## 2. Run one defended experiment

```
python3 experiments/run_experiment.py --n 100 \
  --attacker-source-ip 127.0.0.2 \
  --out-dir results_defended/single_run

python3 experiments/plot_results.py --dir results_defended/single_run
```

The `--attacker-source-ip 127.0.0.2` flag is the only thing different from
the undefended command in `run-test.md` — it's what makes the attacker
bind to the IP the connlimit rule is watching.

Same output layout as the undefended run:

```
results_defended/single_run/
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

**What "working" looks like in `logs/summary.txt`:**
- `[attack]` phase `success` should now stay close to the baseline
  (~100%), not collapse to 0% like the undefended run — the defenses are
  supposed to prevent the denial of service this time.
- `max_open_conns` from `127.0.0.2` should plateau near the connlimit
  (10), instead of climbing to hundreds like the undefended run.
- Check `attacker_stdout.log` — you should see the attacker's held-open
  count get capped and/or connections getting rejected/reset, instead of
  freely climbing to N.

## 3. Run the full defended sweep (N = 20, 50, 100, 200)

```
python3 experiments/run_sweep.py \
  --attacker-source-ip 127.0.0.2 \
  --out-dir results_defended
```

Same structure as the undefended sweep, all under `results_defended/`:

```
results_defended/sweep_N20/...
results_defended/sweep_N50/...
results_defended/sweep_N100/...
results_defended/sweep_N200/...
results_defended/sweep_comparison.png
results_defended/sweep_comparison.csv
results_defended/summary.md
```

**Expected result:** unlike the undefended sweep (where N=50/100/200 all
collapsed the client to 0% success), the defended sweep should keep
`attack_success_pct` close to 100% across all four N values — the whole
point of the defense is that it no longer matters how large N is.

## 4. Compare undefended vs defended

Put the two `summary.md` tables (or the two `sweep_comparison.png`
graphs) side by side in the report — `results/summary.md` vs
`results_defended/summary.md`. The story: same attack script, same N
values, same server hardware — only the defense config differs, and it's
the difference-maker.

## 5. Turning the defense back off

If you need to re-run the undefended baseline again after testing the
defense (e.g. to double check nothing drifted):

```
bash scripts/disable_defense.sh
```

Reverts both defenses and restarts Apache, back to the exact state
`scripts/setup_apache.sh` left it in.

## 6. Troubleshooting

- **`apache2ctl -M | grep reqtimeout` prints nothing after
  `enable_defense.sh`**: run `sudo systemctl restart apache2` again and
  recheck — sometimes the module enable needs the explicit restart to
  take effect rather than a reload.
- **iptables rule doesn't show up / connlimit not capping anything**:
  confirm the kernel module is present with
  `sudo iptables -m connlimit --connlimit-above 1 -p tcp --dport 80 -j REJECT -C INPUT 2>&1`
  (should not complain about an unknown match). Also confirm you passed
  `--attacker-source-ip 127.0.0.2` to `run_experiment.py`/`run_sweep.py`
  — without it the attacker uses the default source IP and never hits
  the rule at all.
- **Legitimate client also gets denied during the defended attack**:
  means the attacker and client ended up on the same source IP. Double
  check `--attacker-source-ip 127.0.0.2` was passed, and that
  `logs/phases.json` for that run shows `"attacker_source_ip": "127.0.0.2"`.
- **Want a stricter/looser connection cap**: edit `CONN_LIMIT` near the
  top of `scripts/enable_defense.sh` (and `scripts/disable_defense.sh`,
  so the removal rule still matches), then re-run both.
