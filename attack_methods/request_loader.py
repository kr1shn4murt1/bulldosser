#!/usr/bin/env python3
"""Shared loader: decodes REQUEST_DATA env var into usable request components."""

import os
import base64
import json
from urllib.parse import urlparse


def load_request_data() -> dict:
    raw = os.environ.get("REQUEST_DATA", "")
    if not raw:
        host = os.environ.get("TARGET_HOST", "target.com")
        port = int(os.environ.get("TARGET_PORT", "443"))
        return {
            "url": f"https://{host}/",
            "method": "GET",
            "host": host,
            "port": port,
            "path": "/",
            "headers": {
                "Host": host,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
            },
            "cookies": {},
            "body": "",
        }

    try:
        data = json.loads(base64.b64decode(raw))
    except Exception:
        data = {}

    parsed = urlparse(data.get("url", "https://target.com/"))
    host = parsed.hostname or os.environ.get("TARGET_HOST", "target.com")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    headers = data.get("headers", {})
    if "Host" not in headers:
        headers["Host"] = host

    return {
        "url": data.get("url", f"https://{host}/"),
        "method": data.get("method", "GET"),
        "host": host,
        "port": port,
        "path": path,
        "scheme": parsed.scheme or "https",
        "headers": headers,
        "cookies": data.get("cookies", {}),
        "body": data.get("body", ""),
    }


def build_cookie_header(cookies: dict) -> str:
    if not cookies:
        return ""
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def build_raw_headers(req: dict, override_method: str = None, override_path: str = None) -> str:
    method = override_method or req["method"]
    path = override_path or req["path"]
    lines = [f"{method} {path} HTTP/1.1"]

    for k, v in req["headers"].items():
        lines.append(f"{k}: {v}")

    cookie_str = build_cookie_header(req["cookies"])
    if cookie_str and "Cookie" not in req["headers"] and "cookie" not in req["headers"]:
        lines.append(f"Cookie: {cookie_str}")

    return "\r\n".join(lines) + "\r\n"
