#!/usr/bin/env python3
"""
curl2request.py — Parse a "Copy as cURL" command into a JSON request template.

Usage:
    python3 curl2request.py target_request.txt -o 01_target.json
    python3 curl2request.py target_request.txt --preview
    cat target_request.txt | python3 curl2request.py - -o 01_target.json
"""

import argparse
import json
import re
import shlex
import sys
from urllib.parse import urlparse


def parse_curl(text: str) -> dict:
    text = text.strip()
    if text.startswith("curl"):
        pass
    elif "curl" in text:
        text = text[text.index("curl"):]

    text = text.replace("\\\n", " ").replace("\\\r\n", " ")
    text = re.sub(r"\s+", " ", text)

    try:
        tokens = shlex.split(text)
    except ValueError:
        tokens = text.split()

    url = ""
    method = "GET"
    headers = {}
    cookies = {}
    body = ""
    method_explicit = False

    i = 0
    while i < len(tokens):
        tok = tokens[i]

        if tok == "curl":
            i += 1
            continue

        if tok in ("-X", "--request") and i + 1 < len(tokens):
            method = tokens[i + 1].upper()
            method_explicit = True
            i += 2
            continue

        if tok in ("-H", "--header") and i + 1 < len(tokens):
            header = tokens[i + 1]
            if ":" in header:
                key, val = header.split(":", 1)
                key = key.strip()
                val = val.strip()
                if key.lower() == "cookie":
                    for pair in val.split(";"):
                        pair = pair.strip()
                        if "=" in pair:
                            ck, cv = pair.split("=", 1)
                            cookies[ck.strip()] = cv.strip()
                else:
                    headers[key] = val
            i += 2
            continue

        if tok in ("-b", "--cookie") and i + 1 < len(tokens):
            for pair in tokens[i + 1].split(";"):
                pair = pair.strip()
                if "=" in pair:
                    ck, cv = pair.split("=", 1)
                    cookies[ck.strip()] = cv.strip()
            i += 2
            continue

        if tok in ("-d", "--data", "--data-raw", "--data-binary", "--data-urlencode") and i + 1 < len(tokens):
            body = tokens[i + 1]
            if not method_explicit:
                method = "POST"
            i += 2
            continue

        if tok == "--url" and i + 1 < len(tokens):
            url = tokens[i + 1]
            i += 2
            continue

        if tok in ("-k", "--insecure", "--compressed", "-s", "--silent",
                    "-v", "--verbose", "-L", "--location", "-i", "--include"):
            i += 1
            continue

        if tok in ("-o", "--output", "--max-time", "--connect-timeout",
                    "-w", "--write-out", "-u", "--user", "--proxy") and i + 1 < len(tokens):
            i += 2
            continue

        if tok.startswith("http://") or tok.startswith("https://") or tok.startswith("'http"):
            url = tok.strip("'\"")
            i += 1
            continue

        i += 1

    parsed = urlparse(url)
    host = parsed.hostname or "target.com"
    target = f"{parsed.scheme}://{host}"

    if "Host" not in headers:
        headers["Host"] = host

    result = {
        "id": "01",
        "name": f"{method} {parsed.path or '/'}",
        "description": f"{method} request to {host}",
        "target": target,
        "method": method,
        "url": url,
        "headers": headers,
        "cookies": cookies,
    }

    if body:
        result["body"] = body

    return result


def main():
    parser = argparse.ArgumentParser(description="Parse curl command into JSON request template")
    parser.add_argument("input", help="File with curl command (use - for stdin)")
    parser.add_argument("-o", "--output", help="Output JSON file")
    parser.add_argument("--preview", action="store_true", help="Print parsed result without saving")
    parser.add_argument("--id", default="01", help="Request ID (default: 01)")
    args = parser.parse_args()

    if args.input == "-":
        text = sys.stdin.read()
    else:
        with open(args.input) as f:
            text = f.read()

    result = parse_curl(text)
    result["id"] = args.id

    formatted = json.dumps(result, indent=2)

    if args.preview or not args.output:
        print(formatted)
        if not args.output:
            print(f"\nParsed: {result['method']} {result['url']}")
            print(f"Headers: {len(result['headers'])}")
            print(f"Cookies: {len(result['cookies'])}")
            if result.get("body"):
                print(f"Body: {len(result['body'])} chars")
            if not args.preview:
                print("\nUse -o <file.json> to save")
        return

    with open(args.output, "w") as f:
        f.write(formatted + "\n")
    print(f"[+] Saved to {args.output}")
    print(f"    {result['method']} {result['url']}")
    print(f"    Headers: {len(result['headers'])} | Cookies: {len(result['cookies'])}")


if __name__ == "__main__":
    main()
