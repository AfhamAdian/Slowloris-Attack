"""
Runs one full baseline -> attack -> recovery experiment for a given
attacker size N, and saves everything (raw CSV logs + phase timing)
into an output directory so plot_results.py can turn it into graphs.

This replaces manually starting/stopping the three scripts by hand:
it starts the monitor and legitimate client, lets them run through
the whole experiment, starts the attacker partway through for exactly
--attack-secs seconds, and lets everything finish on its own.

Run with:
  python3 run_experiment.py --n 100 --out-dir results/single_run

Apache must already be set up (see scripts/setup_apache.sh) and
running before you run this.
"""

import argparse
import json
import os
import subprocess
import sys
import time

PYTHON = sys.executable


def parse_args():
    p = argparse.ArgumentParser(description="Run one baseline/attack/recovery experiment")
    p.add_argument("--n", type=int, default=100, help="number of attacker connections")
    p.add_argument("--target-ip", default="127.0.0.1")
    p.add_argument("--target-port", type=int, default=80)
    p.add_argument("--max-request-workers", type=int, default=30,
                   help="Apache's MaxRequestWorkers, for the graphs' reference line")
    p.add_argument("--baseline-secs", type=float, default=20)
    p.add_argument("--attack-secs", type=float, default=60)
    p.add_argument("--recovery-secs", type=float, default=30)
    p.add_argument("--attacker-interval", type=float, default=5, help="seconds between attacker header sends")
    p.add_argument("--attacker-source-ip", default=None,
                    help="bind the attacker's sockets to this local IP (e.g. 127.0.0.2), so a "
                         "per-IP connection-limit defense can tell it apart from the legitimate "
                         "client. Leave unset for the undefended run.")
    p.add_argument("--client-rate", type=float, default=1, help="seconds between legitimate client requests")
    p.add_argument("--client-timeout", type=float, default=5)
    p.add_argument("--poll-interval", type=float, default=1, help="seconds between monitor samples")
    p.add_argument("--out-dir", default="results/single_run")
    return p.parse_args()


def main():
    args = parse_args()
    logs_dir = os.path.join(args.out_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    total_secs = args.baseline_secs + args.attack_secs + args.recovery_secs
    here = os.path.dirname(os.path.abspath(__file__))
    core_dir = os.path.join(os.path.dirname(here), "core")

    monitor_log = os.path.join(logs_dir, "monitor_log.csv")
    client_log = os.path.join(logs_dir, "client_log.csv")
    attacker_stdout = open(os.path.join(logs_dir, "attacker_stdout.log"), "w")
    monitor_stdout = open(os.path.join(logs_dir, "monitor_stdout.log"), "w")
    client_stdout = open(os.path.join(logs_dir, "client_stdout.log"), "w")

    print(f"=== N={args.n}: baseline={args.baseline_secs}s attack={args.attack_secs}s "
          f"recovery={args.recovery_secs}s -> {args.out_dir} ===")

    baseline_start = time.time()

    monitor_proc = subprocess.Popen(
        [PYTHON, os.path.join(core_dir, "monitor.py"),
         "--target-ip", args.target_ip, "--target-port", str(args.target_port),
         "--poll-interval", str(args.poll_interval), "--duration", str(total_secs),
         "--log-file", monitor_log],
        stdout=monitor_stdout, stderr=subprocess.STDOUT,
    )
    client_proc = subprocess.Popen(
        [PYTHON, os.path.join(core_dir, "legitimate_client.py"),
         "--target-ip", args.target_ip, "--target-port", str(args.target_port),
         "--rate", str(args.client_rate), "--timeout", str(args.client_timeout),
         "--duration", str(total_secs), "--log-file", client_log],
        stdout=client_stdout, stderr=subprocess.STDOUT,
    )

    print(f"[baseline] running for {args.baseline_secs}s ...")
    time.sleep(args.baseline_secs)

    attack_start = time.time()
    print(f"[attack] starting attacker with N={args.n} for {args.attack_secs}s "
          f"(source ip: {args.attacker_source_ip or 'default'}) ...")
    attacker_cmd = [PYTHON, os.path.join(core_dir, "attacker.py"),
                     "--target-ip", args.target_ip, "--target-port", str(args.target_port),
                     "--num-sockets", str(args.n), "--interval", str(args.attacker_interval),
                     "--duration", str(args.attack_secs)]
    if args.attacker_source_ip:
        attacker_cmd += ["--source-ip", args.attacker_source_ip]
    attacker_proc = subprocess.Popen(
        attacker_cmd,
        stdout=attacker_stdout, stderr=subprocess.STDOUT,
    )
    attacker_proc.wait()  # attacker exits on its own after --duration
    recovery_start = time.time()
    print(f"[recovery] attacker stopped, watching recovery for {args.recovery_secs}s ...")

    monitor_proc.wait()
    client_proc.wait()
    end_time = time.time()

    for f in (attacker_stdout, monitor_stdout, client_stdout):
        f.close()

    phases = {
        "n": args.n,
        "max_request_workers": args.max_request_workers,
        "attacker_source_ip": args.attacker_source_ip,
        "baseline_start": baseline_start,
        "attack_start": attack_start,
        "recovery_start": recovery_start,
        "end": end_time,
    }
    with open(os.path.join(logs_dir, "phases.json"), "w") as f:
        json.dump(phases, f, indent=2)

    print(f"Done. Logs + phases.json saved in {logs_dir}")


if __name__ == "__main__":
    main()
