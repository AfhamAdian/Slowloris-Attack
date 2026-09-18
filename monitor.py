"""
Server monitor.

Runs on the server host (or anything that can reach it) and, on a
timer, records how many Apache workers are busy/idle, how many open
connections there are on the server's port, and the server's CPU and
memory usage. This produces the main result graph: worker/connection
count rising to a plateau during the attack while CPU/memory stay flat,
which is what shows this is a connection-exhaustion attack and not a
volumetric one.

Requires: pip install psutil
Requires Apache's mod_status enabled with a URL like /server-status?auto

Run with:  python3 monitor.py
"""

import csv
import re
import subprocess
import time
import urllib.request

import psutil

# --- settings you can tweak -------------------------------------------------
TARGET_IP = "127.0.0.1"
TARGET_PORT = 80
STATUS_URL = f"http://{TARGET_IP}:{TARGET_PORT}/server-status?auto"
POLL_INTERVAL = 2   # seconds between samples
LOG_FILE = "monitor_log.csv"
# -----------------------------------------------------------------------------


def get_worker_counts():
    """
    Fetch Apache's mod_status page (auto/plain-text format) and pull out
    BusyWorkers and IdleWorkers. Returns (busy, idle), or (None, None) if
    the page could not be read (e.g. server is completely stuck).
    """
    try:
        with urllib.request.urlopen(STATUS_URL, timeout=3) as response:
            text = response.read().decode()

        busy = re.search(r"BusyWorkers:\s*(\d+)", text)
        idle = re.search(r"IdleWorkers:\s*(\d+)", text)
        busy = int(busy.group(1)) if busy else None
        idle = int(idle.group(1)) if idle else None
        return busy, idle
    except Exception:
        return None, None


def get_open_connections():
    """
    Count open TCP connections to the target port using `ss -tn`.
    """
    try:
        output = subprocess.run(
            ["ss", "-tn"], capture_output=True, text=True, timeout=3
        ).stdout
        lines = output.splitlines()[1:]  # skip the header line
        matching = [line for line in lines if f":{TARGET_PORT}" in line]
        return len(matching)
    except Exception:
        return None


def main():
    print(f"Polling {STATUS_URL} every {POLL_INTERVAL}s. "
          f"Logging to {LOG_FILE}. Press Ctrl+C to stop.")

    with open(LOG_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["time", "busy_workers", "idle_workers", "open_connections", "cpu_pct", "mem_pct"]
        )

        while True:
            timestamp = time.time()
            busy, idle = get_worker_counts()
            open_conns = get_open_connections()
            cpu_pct = psutil.cpu_percent(interval=None)
            mem_pct = psutil.virtual_memory().percent

            writer.writerow([timestamp, busy, idle, open_conns, cpu_pct, mem_pct])
            f.flush()

            print(f"[monitor] busy={busy} idle={idle} conns={open_conns} "
                  f"cpu={cpu_pct}% mem={mem_pct}%")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
