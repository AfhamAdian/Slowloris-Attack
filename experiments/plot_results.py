"""
Builds the result graphs from one experiment's logs (monitor_log.csv,
client_log.csv, phases.json, all produced by run_experiment.py under
<dir>/logs/), and writes a text summary of the key numbers for the
report. Graphs are saved directly under <dir>; the summary is saved
alongside the raw logs under <dir>/logs/.

Run with:  python3 plot_results.py --dir results/single_run
"""

import argparse
import json
import os

import matplotlib.pyplot as plt
import pandas as pd


def parse_args():
    p = argparse.ArgumentParser(description="Plot one experiment's results")
    p.add_argument("--dir", default="results/single_run", help="directory with monitor_log.csv, client_log.csv, phases.json")
    return p.parse_args()


def mark_phases(ax, attack_t, recovery_t):
    ax.axvline(attack_t, color="red", linestyle="--", linewidth=1)
    ax.axvline(recovery_t, color="green", linestyle="--", linewidth=1)
    ax.text(attack_t, ax.get_ylim()[1], " attack starts", color="red", va="top", fontsize=8)
    ax.text(recovery_t, ax.get_ylim()[1], " attacker stopped", color="green", va="top", fontsize=8)


def phase_slice(df, start, end):
    return df[(df["t"] >= start) & (df["t"] < end)]


def main():
    args = parse_args()
    d = args.dir
    logs_dir = os.path.join(d, "logs")

    with open(os.path.join(logs_dir, "phases.json")) as f:
        phases = json.load(f)

    monitor = pd.read_csv(os.path.join(logs_dir, "monitor_log.csv"))
    client = pd.read_csv(os.path.join(logs_dir, "client_log.csv"))

    t0 = phases["baseline_start"]
    monitor["t"] = monitor["time"] - t0
    client["t"] = client["time"] - t0
    attack_t = phases["attack_start"] - t0
    recovery_t = phases["recovery_start"] - t0
    max_request_workers = phases["max_request_workers"]
    n = phases["n"]

    # --- Graph 1: worker / connection counts over time ----------------------
    # When the pool is fully saturated, Apache can't even answer the
    # mod_status request (busy_workers/idle_workers come back blank).
    # That blank IS the signal, so mark it clearly instead of letting the
    # line just vanish.
    unreachable = monitor["busy_workers"].isna()
    busy_plot = monitor["busy_workers"].fillna(max_request_workers)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(monitor["t"], busy_plot, label="Busy workers", color="crimson")
    ax.plot(monitor["t"], monitor["open_connections"], label="Open connections", color="steelblue")
    ax.axhline(max_request_workers, color="gray", linestyle=":", linewidth=1,
               label=f"MaxRequestWorkers ({max_request_workers})")
    ax.fill_between(monitor["t"], 0, monitor["open_connections"].max(),
                     where=unreachable, color="crimson", alpha=0.08,
                     label="mod_status unreachable (fully saturated)")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Count")
    ax.set_title(f"Apache worker exhaustion vs time (N={n})")
    ax.legend(fontsize=8)
    mark_phases(ax, attack_t, recovery_t)
    fig.tight_layout()
    fig.savefig(os.path.join(d, "1_worker_saturation.png"), dpi=150)
    plt.close(fig)

    # --- Graph 2: CPU / memory over time -------------------------------------
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(monitor["t"], monitor["cpu_pct"], label="CPU %", color="darkorange")
    ax.plot(monitor["t"], monitor["mem_pct"], label="Memory %", color="purple")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Usage (%)")
    ax.set_ylim(0, 100)
    ax.set_title(f"Server CPU & memory usage vs time (N={n}) - stays flat: not volumetric")
    ax.legend()
    mark_phases(ax, attack_t, recovery_t)
    fig.tight_layout()
    fig.savefig(os.path.join(d, "2_cpu_mem.png"), dpi=150)
    plt.close(fig)

    # --- Graph 3: client success rate over time (5s rolling buckets) --------
    client["bucket"] = (client["t"] // 5) * 5
    success_rate = client.groupby("bucket")["status"].apply(lambda s: (s == "success").mean() * 100)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(success_rate.index, success_rate.values, color="seagreen", marker="o", markersize=2)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Success rate (%)")
    ax.set_ylim(-5, 105)
    ax.set_title(f"Legitimate client success rate vs time (N={n}, 5s buckets)")
    mark_phases(ax, attack_t, recovery_t)
    fig.tight_layout()
    fig.savefig(os.path.join(d, "3_client_success_rate.png"), dpi=150)
    plt.close(fig)

    # --- Graph 4: client latency over time -----------------------------------
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(client["t"], client["latency_seconds"], color="black", linewidth=0.8)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Response time (s)")
    ax.set_title(f"Legitimate client response time vs time (N={n})")
    mark_phases(ax, attack_t, recovery_t)
    fig.tight_layout()
    fig.savefig(os.path.join(d, "4_client_latency.png"), dpi=150)
    plt.close(fig)

    # --- Text summary ---------------------------------------------------------
    phase_windows = {
        "baseline": (0, attack_t),
        "attack": (attack_t, recovery_t),
        "recovery": (recovery_t, client["t"].max() + 1),
    }

    lines = [f"=== Summary for N={n} ({d}) ==="]
    summary = {"n": n}
    for name, (start, end) in phase_windows.items():
        c = phase_slice(client, start, end)
        m = phase_slice(monitor, start, end)
        success_pct = (c["status"] == "success").mean() * 100 if len(c) else float("nan")
        avg_latency = c["latency_seconds"].mean() if len(c) else float("nan")
        max_busy = m["busy_workers"].max() if len(m) else float("nan")
        max_conns = m["open_connections"].max() if len(m) else float("nan")
        avg_cpu = m["cpu_pct"].mean() if len(m) else float("nan")
        line = (f"[{name}] duration={end-start:.0f}s  success={success_pct:.1f}%  "
                f"avg_latency={avg_latency:.3f}s  max_busy_workers={max_busy}  "
                f"max_open_conns={max_conns}  avg_cpu={avg_cpu:.1f}%")
        lines.append(line)
        summary[f"{name}_success_pct"] = float(success_pct)
        summary[f"{name}_avg_latency"] = float(avg_latency)
        summary[f"{name}_max_busy_workers"] = float(max_busy) if pd.notna(max_busy) else None
        summary[f"{name}_max_open_conns"] = float(max_conns) if pd.notna(max_conns) else None
        summary[f"{name}_avg_cpu"] = float(avg_cpu)

    # time from attack start to first fully-saturated sample
    attack_window = monitor[monitor["t"] >= attack_t]
    saturated = attack_window[attack_window["busy_workers"].isna() |
                               (attack_window["busy_workers"] >= max_request_workers)]
    time_to_saturation = float(saturated["t"].iloc[0] - attack_t) if len(saturated) else None
    summary["time_to_saturation"] = time_to_saturation
    lines.append(f"Time from attack start to worker pool saturation: "
                 f"{time_to_saturation:.1f}s" if time_to_saturation is not None else
                 "Worker pool never fully saturated during the attack window")

    summary_text = "\n".join(lines)
    print(summary_text)
    with open(os.path.join(logs_dir, "summary.txt"), "w") as f:
        f.write(summary_text + "\n")
    with open(os.path.join(logs_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
