# Slowloris-Attack

Slowloris DoS demonstration. See `slowloris-project-design.md` for the full
project design. This implements the undefended-server phase: attacker,
legitimate client, and monitor. (Server-side defense config is a separate,
later step and is not included here yet.)

## Setup

1. Point an Apache server (prefork MPM, `mod_status` enabled) at whatever
   machine `TARGET_IP` refers to in each script.
2. Install the one dependency (used by `monitor.py` for CPU/memory stats):

   ```
   pip install -r requirements.txt
   ```

## Scripts

- `attacker.py` — opens many connections and trickles one header line at a
  time on each, never completing the request. Edit `TARGET_IP`,
  `NUM_SOCKETS`, `INTERVAL` at the top of the file.
- `legitimate_client.py` — sends one normal request per second and logs
  success/failure and latency to `client_log.csv`.
- `monitor.py` — polls Apache's `/server-status?auto` and `ss -tn` every 2
  seconds and logs worker count, connection count, CPU%, and memory% to
  `monitor_log.csv`.

Run each in its own terminal (order: monitor and client first, attacker
last) with `python3 <script>.py`, and stop any of them with Ctrl+C.
