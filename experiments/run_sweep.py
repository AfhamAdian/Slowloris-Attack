"""
Runs the full baseline -> attack -> recovery experiment once per value
of N (number of attacker connections), each into its own results
directory, then plots each one and builds one extra comparison graph
across all of them (time-to-saturation and min success rate vs N).

This is the "sweep" step from the design doc (Section 9, step 4): it
shows how much N matters relative to the server's worker pool.

Run with:  python3 run_sweep.py
Or with options:  python3 run_sweep.py --ns 20 50 100 200 --out-dir results/sweep

Apache must already be set up (see scripts/setup_apache.sh) and
running before you run this. Runs are sequential (same server), so
this takes N_VALUES * (baseline+attack+recovery) seconds in total.
"""

import argparse
import json
import os
import subprocess
import sys
import time

import matplotlib.pyplot as plt

PYTHON = sys.executable
HERE = os.path.dirname(os.path.abspath(__file__))


def parse_args():
    p = argparse.ArgumentParser(description="Run the N sweep: 20 -> 50 -> 100 -> 200")
    p.add_argument("--ns", type=int, nargs="+", default=[20, 50, 100, 200])
    p.add_argument("--out-dir", default="results")
    p.add_argument("--baseline-secs", type=float, default=20)
    p.add_argument("--attack-secs", type=float, default=60)
    p.add_argument("--recovery-secs", type=float, default=30)
    p.add_argument("--max-request-workers", type=int, default=30)
    p.add_argument("--attacker-source-ip", default=None,
                    help="passed through to run_experiment.py; set to 127.0.0.2 for a defended "
                         "run so the connlimit rule can tell the attacker apart from the client")
    p.add_argument("--cooldown-secs", type=float, default=None,
                    help="pause between sweep steps, so the previous step's closed attacker "
                         "connections drain out of the kernel's conntrack table before the next "
                         "step starts. Needed when --attacker-source-ip is set: otherwise the "
                         "iptables connlimit rule still counts the previous step's connections "
                         "(TIME_WAIT can linger 60-120s) and rejects the next step's attacker "
                         "outright, making every step but the first look artificially defended. "
                         "Default: 130s when --attacker-source-ip is set, 0s otherwise.")
    return p.parse_args()


def format_max_busy(value, max_request_workers):
    if value is None:
        return "pool exhausted"
    value = int(value)
    if value < max_request_workers:
        return f"{value} (below the {max_request_workers}-worker pool — no denial)"
    return str(value)


def build_summary_markdown(summaries, max_request_workers):
    lines = [
        "# Sweep Summary",
        "",
        "Attack-phase numbers for each attacker size N, from the "
        f"baseline/attack/recovery experiment (Apache `MaxRequestWorkers={max_request_workers}`).",
        "",
        "| N | Client success rate | Avg latency | Max busy workers | Max open conns |",
        "|---|---|---|---|---|",
    ]
    for s in summaries:
        n = s["n"]
        success = s["attack_success_pct"]
        latency = s["attack_avg_latency"]
        max_busy = format_max_busy(s["attack_max_busy_workers"], max_request_workers)
        max_conns = int(s["attack_max_open_conns"]) if s["attack_max_open_conns"] is not None else "-"
        lines.append(f"| {n} | {success:.0f}% | {latency:.2f}s | {max_busy} | {max_conns} |")
    lines.append("")
    return "\n".join(lines)


def main():
    args = parse_args()
    cooldown_secs = args.cooldown_secs
    if cooldown_secs is None:
        cooldown_secs = 130 if args.attacker_source_ip else 0
    summaries = []

    for i, n in enumerate(args.ns):
        if i > 0 and cooldown_secs > 0:
            print(f"\nCooling down for {cooldown_secs:.0f}s so the previous step's attacker "
                  f"connections drain out of conntrack before the next step starts ...")
            time.sleep(cooldown_secs)

        run_dir = os.path.join(args.out_dir, f"sweep_N{n}")
        print(f"\n########## N={n} -> {run_dir} ##########")

        run_cmd = [
            PYTHON, os.path.join(HERE, "run_experiment.py"),
            "--n", str(n),
            "--out-dir", run_dir,
            "--baseline-secs", str(args.baseline_secs),
            "--attack-secs", str(args.attack_secs),
            "--recovery-secs", str(args.recovery_secs),
            "--max-request-workers", str(args.max_request_workers),
        ]
        if args.attacker_source_ip:
            run_cmd += ["--attacker-source-ip", args.attacker_source_ip]
        subprocess.run(run_cmd, check=True)

        subprocess.run([
            PYTHON, os.path.join(HERE, "plot_results.py"),
            "--dir", run_dir,
        ], check=True)

        with open(os.path.join(run_dir, "logs", "summary.json")) as f:
            summaries.append(json.load(f))

    # --- comparison graph across all N values --------------------------------
    ns = [s["n"] for s in summaries]
    time_to_sat = [s["time_to_saturation"] if s["time_to_saturation"] is not None else float("nan") for s in summaries]
    attack_success = [s["attack_success_pct"] for s in summaries]

    saturated_at_least_once = any(v == v for v in time_to_sat)  # v == v is False only for NaN

    if saturated_at_least_once:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        ax1.plot(ns, time_to_sat, marker="o", color="crimson")
        ax1.set_xlabel("N (attacker connections)")
        ax1.set_ylabel("Time to saturation (s)")
        ax1.set_title("Time to saturation vs N")
    else:
        # the worker pool never saturated at any tested N (e.g. a working
        # defense), so there is no "time to saturation" curve to draw -
        # drop that panel instead of leaving it blank
        fig, ax2 = plt.subplots(1, 1, figsize=(7, 5))

    ax2.plot(ns, attack_success, marker="o", color="seagreen")
    ax2.set_xlabel("N (attacker connections)")
    ax2.set_ylabel("Client success rate during attack (%)")
    ax2.set_ylim(-5, 105)
    ax2.set_title("Legitimate client success rate during attack vs N")

    fig.tight_layout()
    comparison_path = os.path.join(args.out_dir, "sweep_comparison.png")
    fig.savefig(comparison_path, dpi=150)
    print(f"\nSaved comparison graph to {comparison_path}")

    # --- comparison table ------------------------------------------------------
    table_path = os.path.join(args.out_dir, "sweep_comparison.csv")
    with open(table_path, "w") as f:
        f.write("n,time_to_saturation_s,attack_success_pct,attack_avg_latency_s,attack_max_busy_workers,attack_max_open_conns\n")
        for s in summaries:
            f.write(f"{s['n']},{s['time_to_saturation']},{s['attack_success_pct']:.1f},"
                    f"{s['attack_avg_latency']:.3f},{s['attack_max_busy_workers']},{s['attack_max_open_conns']}\n")
    print(f"Saved comparison table to {table_path}")

    # --- markdown summary --------------------------------------------------
    summary_md_path = os.path.join(args.out_dir, "summary.md")
    with open(summary_md_path, "w") as f:
        f.write(build_summary_markdown(summaries, args.max_request_workers))
    print(f"Saved markdown summary to {summary_md_path}")


if __name__ == "__main__":
    main()
