"""
Legitimate client.

Stands in for a real user browsing the site while the attack is
running. It sends one complete, ordinary HTTP request at a steady
rate, forever (or for a fixed duration), and logs whether each request
succeeded or timed out along with how long it took. This log is the
proof that an attack actually denies service to real users, not just a
change in some internal server counter.

Run with:  python3 legitimate_client.py
Or with options:  python3 legitimate_client.py --rate 1 --duration 120
"""

import argparse
import csv
import http.client
import time


def parse_args():
    p = argparse.ArgumentParser(description="Legitimate client")
    p.add_argument("--target-ip", default="127.0.0.1")
    p.add_argument("--target-port", type=int, default=80)
    p.add_argument("--timeout", type=float, default=5, help="seconds to wait before giving up on a request")
    p.add_argument("--rate", type=float, default=1, help="seconds to sleep between requests")
    p.add_argument("--duration", type=float, default=None, help="stop after this many seconds (default: run forever)")
    p.add_argument("--log-file", default="client_log.csv")
    return p.parse_args()


def send_one_request(target_ip, target_port, timeout):
    """
    Send a single complete GET / request and report what happened.
    Returns a tuple: (status, latency_seconds, status_code_or_None)
    status is "success" or "failure".
    """
    start = time.time()
    try:
        conn = http.client.HTTPConnection(target_ip, target_port, timeout=timeout)
        conn.request("GET", "/")
        response = conn.getresponse()
        code = response.status
        response.read()
        conn.close()
        latency = time.time() - start
        return "success", latency, code
    except (OSError, http.client.HTTPException):
        # covers connection refused, timeout, connection reset, etc.
        latency = time.time() - start
        return "failure", latency, None


def main():
    args = parse_args()
    end_time = time.time() + args.duration if args.duration else None

    print(f"Requesting http://{args.target_ip}:{args.target_port}/ every {args.rate}s. "
          f"Logging to {args.log_file}. Press Ctrl+C to stop.")

    with open(args.log_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "status", "latency_seconds", "status_code"])

        while end_time is None or time.time() < end_time:
            timestamp = time.time()
            status, latency, code = send_one_request(args.target_ip, args.target_port, args.timeout)

            writer.writerow([timestamp, status, round(latency, 3), code])
            f.flush()

            print(f"[client] {status} in {latency:.3f}s (code={code})")
            time.sleep(args.rate)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
