"""
Legitimate client.

Stands in for a real user browsing the site while the attack (or the
defense) is running. It sends one complete, ordinary HTTP request at a
steady rate, forever, and logs whether each request succeeded or timed
out along with how long it took. This log is the proof that an attack
actually denies service to real users, not just a change in some
internal server counter.

Run with:  python3 legitimate_client.py
"""

import csv
import http.client
import time

# --- settings you can tweak -------------------------------------------------
TARGET_IP = "127.0.0.1"   # IP of the target web server
TARGET_PORT = 80          # port the web server listens on
REQUEST_TIMEOUT = 5       # seconds to wait for a response before giving up
RATE = 1                  # seconds to sleep between requests
LOG_FILE = "client_log.csv"
# -----------------------------------------------------------------------------


def send_one_request():
    """
    Send a single complete GET / request and report what happened.
    Returns a tuple: (status, latency_seconds, status_code_or_None)
    status is "success" or "failure".
    """
    start = time.time()
    try:
        conn = http.client.HTTPConnection(TARGET_IP, TARGET_PORT, timeout=REQUEST_TIMEOUT)
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
    print(f"Requesting http://{TARGET_IP}:{TARGET_PORT}/ every {RATE}s. "
          f"Logging to {LOG_FILE}. Press Ctrl+C to stop.")

    with open(LOG_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "status", "latency_seconds", "status_code"])

        while True:
            timestamp = time.time()
            status, latency, code = send_one_request()

            writer.writerow([timestamp, status, round(latency, 3), code])
            f.flush()

            print(f"[client] {status} in {latency:.3f}s (code={code})")
            time.sleep(RATE)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
