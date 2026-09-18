# Graph Interpretation — Slowloris N-Sweep (N=20, 50, 100, 200)

Setup, for reference (from `scripts/setup_apache.sh` and `experiments/run_experiment.py`):
Apache prefork MPM, `StartServers 5`, `MinSpareServers 5`, `MaxRequestWorkers 30`, `mod_reqtimeout` **disabled** (undefended baseline). Each run is baseline (20s) → attack (60s) → recovery (30s). The attacker (`core/attacker.py`) opens N sockets, sends one harmless header every 5s, never finishes the request — so each held socket pins one Apache worker indefinitely without using any real CPU/bandwidth. The legitimate client (`core/legitimate_client.py`) requests `GET /` once a second with a 5s timeout. The monitor (`core/monitor.py`) polls Apache's own `/server-status?auto` (itself an HTTP request competing for a worker) plus `ss -tn` every second.

Overall verdict: **all four sweeps behave exactly as this attack model predicts**, with a few artifacts worth calling out explicitly rather than reading as "attack behavior." Those are noted per-graph below.

---

## N = 20 — below the worker pool, no denial

- **Graph 1 (worker/connection saturation):** Busy workers spike to exactly 30 for a single sample right as the attack starts, then settle down to 21 for the rest of the attack, before dropping to ~1-2 after the attacker stops. Open connections spike to 45 then settle at 40.
  - The settle-down to 21 (not 30) is correct: only 20 attacker sockets exist, so at most ~20-23 workers can ever be pinned by them; the pool (30) is never actually exhausted.
  - The momentary touch of exactly 30 at the very first sample is a real but transient effect, not sustained exhaustion: Apache's prefork MPM only has `StartServers=5` warm workers; 20 near-simultaneous new connections arriving at once briefly queue while Apache spawns additional child processes (spawning is throttled to roughly one new child per second by design), so busy-worker count and the mod_status sample coincide with a short burst before it settles. This is why the "time to saturation" metric (see sweep comparison, below) fires almost immediately even though N=20 never denies service.
  - Open connections settling at 40, not 20: `ss -tn` counts every socket touching port 80 in either direction, including the monitor's own repeated status polls and the legitimate client's own connections, not just the attacker's 20. That extra ~20 is background traffic from the measurement tools themselves.

- **Graph 3 (success rate):** Flat 100% throughout — correct, since the pool never saturates, every legitimate request still gets served.

- **Graph 4 (latency):** A single upward spike to ~4.95s exactly at t≈20 (attack start), immediately back to ~0.001s afterward. Checking `client_log.csv` directly confirms it's one specific request at t=20.09s that still returned HTTP 200 (i.e. it succeeded, just slowly) — it is not a failure, and the success-rate graph correctly shows 100% for that bucket. This lines up with the worker-spawn burst explained above: that one legitimate request got stuck behind Apache spinning up extra workers to absorb the sudden burst of 20 new connections, then latency returns to instant once the spawn settles. It's a one-sample transient, not a trend — the line looks like a "spike" mainly because matplotlib draws a straight segment between two isolated points that are ~1s apart.

- **Graph 2 (CPU/memory):** Flat, noisy CPU around 1-10%, memory pinned around 76-78% the whole run (no reaction to the attack at all). The ~77% memory floor is the host's pre-existing baseline load (whatever else is resident on the test machine), not something the attack caused — it's flat before, during, and after the attack, which is itself the intended point of this graph (labelled "not volumetric" in the title): a Slowloris attack consumes worker slots, not CPU or memory bandwidth.

## N = 50 — full saturation, complete denial

- **Graph 1:** Busy workers jump straight to 30 and stay pinned there for the entire 60s attack window (the shaded "mod_status unreachable" band confirms Apache couldn't even answer its own status page — all 30 workers are stuck holding attacker connections). Open connections climb steadily from ~104 to ~150 over the attack window, then drop to ~1 instantly the moment the attacker stops.
  - The pinned-at-30 line is the actual denial-of-service condition: 50 attacker sockets is enough to exceed the 30-worker pool, so literally every worker is captured and none are left for anyone else.
  - The **steady climb** in open connections during the attack (not a flat plateau) is a measurement artifact, not attacker growth: `core/attacker.py` keeps a fixed pool of ~50 sockets (it only replaces ones that get closed), so the attacker side is not the source of growth. The growth instead comes from the monitor's own status-page probes and the legitimate client's own requests — both are themselves HTTP requests against the now-fully-saturated server, so they also queue at the TCP level without ever getting a worker, and those queued/timing-out sockets accumulate (confirmed against `monitor_log.csv`: open connections increase by roughly 1 count per second, matching the combined rate of the monitor's ~1/s polling and the client's ~1-per-5-6s failed attempts during the attack). This is the tool's own traffic piling up against a wall, not a growing attack.
  - The instant drop back to ~1 at the "attacker stopped" line shows recovery is immediate and complete: since nothing was resource-starved (no memory/CPU pressure, see Graph 2), Apache frees all 30 workers the moment the attacker's connections close, with no lingering backlog.

- **Graph 3 (success rate):** Sharp drop from 100% to 0% right at attack start, flat 0% through the whole attack, sharp recovery to 100% right after the attacker stops. This is the clean, expected step function for a fully-successful DoS — every legitimate request during the window fails.

- **Graph 4 (latency):** Jumps to a flat plateau at exactly 5.0s (the client's configured timeout) for the whole attack, then drops back to ~0. The flat top at exactly 5.0s (not some other value) is a direct readout of `--client-timeout=5`: every request during the attack blocks for the full timeout window and then gives up, so latency pins at the timeout value rather than showing variation. This also explains why there are far fewer sample points during the attack phase than during baseline/recovery in the raw log (client_log.csv has ~10 attack-phase rows vs. ~20-30 baseline/recovery rows) — at 1 request/s + up to 5s timeout, the client can only complete roughly one request per 6s while the server is unresponsive, so the graph's attack segment is naturally sparser, which is why it renders as a flat straight line rather than a noisy plateau.

- **Graph 2:** Same flat CPU/memory story as N=20 — confirms the attack is connection-exhaustion, not volumetric, regardless of N.

## N = 100 — same shape as N=50, just double the standing connections

- **Graph 1:** Identical pattern to N=50: busy workers pinned at 30 through the entire attack, open connections climbing from ~205 to ~250 (again roughly +1/s from the monitor+client's own queued probes against the saturated server, same mechanism as N=50, just against a larger fixed attacker floor of ~100 sockets instead of ~50), then an instant drop to ~1 on recovery.
- **Graphs 3 & 4:** Identical step-function shape to N=50 (0% success, 5.0s latency plateau during the attack) — once the pool is exhausted, doubling N doesn't make the denial "more denied"; 100 sockets and 50 sockets both simply exceed the 30-worker limit, so the client-facing effect saturates at "fully blocked" for both.
- **Graph 2:** Flat CPU/memory, same as the other runs.

Takeaway: N=50 and N=100 are functionally indistinguishable from the legitimate client's point of view — this is expected once N clears the `MaxRequestWorkers` threshold, since the pool can't be "more exhausted" than 100%.

## N = 200 — same saturation, but a 9.1% success reading that is measurement noise

- **Graph 1:** Same shape again, scaled up: connections climb from ~405 to ~450 (same +1/s monitor/client queuing artifact as the other saturated runs), busy workers pinned at 30, instant recovery.
- **Graph 3 & 4:** Visually identical 0%→100% step / 5s-latency-plateau shape to N=50 and N=100 in the *time-series* graphs.
- **The 9.1% figure in `summary.md`/`sweep_comparison.png` for N=200 (vs. 0% for N=50 and N=100) is not a real trend of "more attackers denying fewer requests."** Checking `client_log.csv` directly: every single client request logged strictly inside the 60s attack window is a `failure` (10/10, all pinned at the 5.0s timeout). The one `success` that gets counted into the "attack" bucket lands at t=80.14s, just 0.01s before the phase boundary (`recovery_start` = 80.15s) recorded in `phases.json`. This is a race between two independently-clocked events: `run_experiment.py` stamps `recovery_start` only after `attacker_proc.wait()` returns, but the attacker's own sockets are actually torn down (and the worker pool freed) a moment earlier, inside the attacker process's shutdown, before the parent process observes its exit and writes the timestamp. Because `plot_results.py` buckets purely by wall-clock time against that timestamp, one lucky client request that happened to fire in that few-hundred-millisecond gap gets counted as part of the "attack" phase even though the server had already started recovering. With only 11 total attack-phase samples for N=200, that single race-condition success is enough to move the percentage from 0% to 9.1%.
  - This does **not** mean N=200 is a "weaker" attack than N=50/N=100 — all three produce identical, complete denial while actually running. It's an artifact of (a) using wall-clock phase boundaries recorded by a separate process rather than a clean signal from the attacker itself, and (b) the small sample size (n=11) in the attack window, which makes a single sample's classification move the percentage by ~9 points.

## The cross-N comparison graph (`sweep_comparison.png`)

- **Right panel (client success rate vs N):** Correct signal at a coarse level — a cliff from 100% (N=20, below the pool) down to ~0% (N≥50, pool exceeded). The apparent uptick at N=200 (0% → 9.1%) is the boundary-timing artifact described above, not a real change in attack effectiveness; all N≥50 runs are equally, fully effective. If re-run, or if the phase boundary were taken from the attacker's own last-active timestamp instead of the parent process's `wait()` return, that data point would very likely also show 0%.
- **Left panel (time to saturation vs N):** Effectively flat and non-monotonic noise (0.243s–0.251s across N=20→200, a spread smaller than the monitor's own 1-second poll interval). This metric is not meaningful here: `plot_results.py` computes it as "time of the first monitor sample after attack start where the pool already looks saturated," and because the monitor only samples once per second, saturation for every N in this sweep (even N=20's transient worker-spawn burst) is detected on the very first poll after the attacker starts. The metric can't resolve any real difference between N values at this poll rate — the zig-zag shape is sampling jitter, not a property of the attack.

## Summary of "why" for each recurring feature

| Observation | Cause |
|---|---|
| Busy workers pin exactly at 30 for N≥50 | `MaxRequestWorkers=30`; every worker is captured by an attacker connection that never completes its request |
| N=20 never fully saturates (settles at 21, not 30) | Only 20 attacker sockets exist — can't exceed a 30-worker pool by itself |
| Momentary spike to 30 at attack start even for N=20 | Prefork MPM spawns new child workers gradually; a burst of new connections briefly queues during spawn-up |
| Open connections *climb* steadily during a saturated attack, instead of staying flat at N | Not attacker growth (attacker holds a fixed ~N sockets) — it's the monitor's own status polls and the client's own failed requests queuing against the saturated server and being counted by `ss -tn` |
| Latency pins at exactly 5.0s during saturation | Equals `--client-timeout 5`; every blocked request runs out the full timeout |
| Success rate is a clean step function (100%→0%→100%) | The attack is binary once the pool is exceeded: either a worker is free or it isn't |
| CPU/memory stay flat throughout every run | Slowloris is a connection-exhaustion attack, not a volumetric one — no extra CPU or bandwidth is consumed by holding a socket open |
| Recovery is instantaneous in every run | No real resource exhaustion (CPU/mem/disk) occurred, so nothing needs to "cool down" — freeing the sockets immediately frees the workers |
| N=200 shows 9.1% "success" during attack instead of 0% | A single request landed in a sub-second race window between the attacker's actual socket teardown and the orchestrator's recorded `recovery_start` timestamp — a phase-boundary measurement artifact, not weaker denial |
| "Time to saturation vs N" comparison graph is flat/noisy | The monitor's 1-second poll interval is too coarse to resolve any real timing difference; saturation is detected on the first poll for every N tested |
