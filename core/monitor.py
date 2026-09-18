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
Or with options:  python3 monitor.py --poll-interval 1 --duration 120
"""

import argparse
import csv
import re
import subprocess
import time
import urllib.request

import psutil


def parse_args():
    p = argparse.ArgumentParser(description="Server monitor")
    p.add_argument("--target-ip", default="127.0.0.1")
    p.add_argument("--target-port", type=int, default=80)
    p.add_argument("--poll-interval", type=float, default=1, help="seconds between samples")
    p.add_argument("--duration", type=float, default=None, help="stop after this many seconds (default: run forever)")
    p.add_argument("--log-file", default="monitor_log.csv")
    return p.parse_args()


def get_worker_counts(status_url):
    """
    Fetch Apache's mod_status page (auto/plain-text format) and pull out
    BusyWorkers and IdleWorkers. Returns (busy, idle), or (None, None) if
    the page could not be read (e.g. server is completely stuck).
    """
    try:
        with urllib.request.urlopen(status_url, timeout=3) as response:
            text = response.read().decode()

        busy = re.search(r"BusyWorkers:\s*(\d+)", text)
        idle = re.search(r"IdleWorkers:\s*(\d+)", text)
        busy = int(busy.group(1)) if busy else None
        idle = int(idle.group(1)) if idle else None
        return busy, idle
    except Exception:
        return None, None


def get_open_connections(target_port):
    """
    Count open TCP connections to the target port using `ss -tn`,
    filtered on the exact port (not a substring match, which would
    also catch unrelated ephemeral ports that happen to contain the
    same digits).
    """
    try:
        output = subprocess.run(
            ["ss", "-tn", f"( dport = :{target_port} or sport = :{target_port} )"],
            capture_output=True, text=True, timeout=3,
        ).stdout
        lines = output.splitlines()[1:]  # skip the header line
        return len([line for line in lines if line.strip()])
    except Exception:
        return None


def main():
    args = parse_args()
    status_url = f"http://{args.target_ip}:{args.target_port}/server-status?auto"
    end_time = time.time() + args.duration if args.duration else None

    print(f"Polling {status_url} every {args.poll_interval}s. "
          f"Logging to {args.log_file}. Press Ctrl+C to stop.")

    with open(args.log_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["time", "busy_workers", "idle_workers", "open_connections", "cpu_pct", "mem_pct"]
        )

        while end_time is None or time.time() < end_time:
            timestamp = time.time()
            busy, idle = get_worker_counts(status_url)
            open_conns = get_open_connections(args.target_port)
            cpu_pct = psutil.cpu_percent(interval=None)
            mem_pct = psutil.virtual_memory().percent

            writer.writerow([timestamp, busy, idle, open_conns, cpu_pct, mem_pct])
            f.flush()

            print(f"[monitor] busy={busy} idle={idle} conns={open_conns} "
                  f"cpu={cpu_pct}% mem={mem_pct}%")
            time.sleep(args.poll_interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
