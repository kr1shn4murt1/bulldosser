#!/usr/bin/env python3
"""
HTTP Request Executor
Executes HTTP requests stored in JSON files.

Usage:
    ./execute_request.py <request_file.json>
    ./execute_request.py --list
    ./execute_request.py --all
"""

import json
import sys
import os
import argparse
from pathlib import Path
from datetime import datetime
import urllib.parse
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

# Suppress SSL warnings for testing
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class RequestExecutor:
    def __init__(self, request_file, output_dir="results"):
        self.request_file = request_file
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.request_data = None

    def load_request(self):
        """Load request from JSON file"""
        with open(self.request_file, 'r') as f:
            self.request_data = json.load(f)
        return self.request_data

    def execute(self, verify_ssl=False, follow_redirects=True, timeout=30, proxy=None):
        """Execute the HTTP request"""
        if not self.request_data:
            self.load_request()

        req = self.request_data

        print(f"\n{'='*80}")
        print(f"[*] Executing Request: {req['name']}")
        print(f"[*] ID: {req['id']}")
        print(f"[*] Target: {req['target']}")
        print(f"[*] Description: {req['description']}")
        print(f"{'='*80}\n")

        # Prepare request parameters
        method = req['method']
        url = req['url']
        headers = req['headers']

        # Handle request data
        if 'data_raw' in req:
            data = req['data_raw']
        elif 'data_parsed' in req:
            data = req['data_parsed']
        else:
            data = None

        # Prepare proxies if specified
        proxies = None
        if proxy:
            proxies = {
                'http': proxy,
                'https': proxy
            }

        # Execute request
        try:
            print(f"[*] Sending {method} request to: {url}")
            start_time = datetime.now()

            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                data=data,
                verify=verify_ssl,
                allow_redirects=follow_redirects,
                timeout=timeout,
                proxies=proxies
            )

            end_time = datetime.now()
            elapsed = (end_time - start_time).total_seconds()

            # Display response info
            print(f"\n[+] Response received in {elapsed:.2f}s")
            print(f"[+] Status Code: {response.status_code} {response.reason}")
            print(f"[+] Content-Type: {response.headers.get('Content-Type', 'N/A')}")
            print(f"[+] Content-Length: {len(response.content)} bytes")

            # Display response headers
            print(f"\n[*] Response Headers:")
            for header, value in response.headers.items():
                print(f"    {header}: {value}")

            # Save results
            self._save_results(response, elapsed)

            # Display preview of response body
            print(f"\n[*] Response Body Preview (first 500 chars):")
            print("-" * 80)
            try:
                body_text = response.text[:500]
                print(body_text)
                if len(response.text) > 500:
                    print(f"\n... ({len(response.text) - 500} more characters)")
            except:
                print("[Binary content - see saved file]")
            print("-" * 80)

            return response

        except requests.exceptions.RequestException as e:
            print(f"\n[!] Request failed: {str(e)}")
            return None

    def _save_results(self, response, elapsed):
        """Save request and response to files"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        req_id = self.request_data['id']
        base_filename = f"{req_id}_{timestamp}"

        # Save response body
        body_file = self.output_dir / f"{base_filename}_response.html"
        with open(body_file, 'wb') as f:
            f.write(response.content)

        # Save metadata
        meta_file = self.output_dir / f"{base_filename}_meta.json"
        metadata = {
            "request": {
                "id": req_id,
                "name": self.request_data['name'],
                "url": self.request_data['url'],
                "method": self.request_data['method'],
                "timestamp": timestamp
            },
            "response": {
                "status_code": response.status_code,
                "reason": response.reason,
                "headers": dict(response.headers),
                "elapsed_seconds": elapsed,
                "content_length": len(response.content)
            }
        }

        with open(meta_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        print(f"\n[*] Results saved:")
        print(f"    - Response body: {body_file}")
        print(f"    - Metadata: {meta_file}")

    def generate_curl_command(self):
        """Generate equivalent curl command"""
        if not self.request_data:
            self.load_request()

        req = self.request_data
        cmd_parts = ["curl", f"'{req['url']}'"]

        # Add method
        if req['method'] != 'GET':
            cmd_parts.extend(["-X", req['method']])

        # Add headers
        for header, value in req['headers'].items():
            cmd_parts.extend(["-H", f"'{header}: {value}'"])

        # Add data
        if 'data_raw' in req:
            cmd_parts.extend(["--data-raw", f"'{req['data_raw']}'"])

        return " \\\n  ".join(cmd_parts)


def list_requests(requests_dir="."):
    """List all available request files"""
    requests_path = Path(requests_dir)
    json_files = sorted(requests_path.glob("*.json"))

    if not json_files:
        print("[!] No request files found")
        return []

    print(f"\n{'='*80}")
    print("Available Requests:")
    print(f"{'='*80}\n")

    requests_list = []
    for json_file in json_files:
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
                requests_list.append((json_file, data))
                print(f"[{data['id']}] {json_file.name}")
                print(f"    Name: {data['name']}")
                print(f"    Target: {data['target']}")
                print(f"    Method: {data['method']} {data['url']}")
                print(f"    Description: {data['description']}")
                print()
        except Exception as e:
            print(f"[!] Error reading {json_file}: {e}")

    return requests_list


def main():
    parser = argparse.ArgumentParser(
        description="Execute HTTP requests from JSON files",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('request_file', nargs='?', help='JSON request file to execute')
    parser.add_argument('--list', action='store_true', help='List all available requests')
    parser.add_argument('--all', action='store_true', help='Execute all requests in sequence')
    parser.add_argument('--curl', action='store_true', help='Generate curl command instead of executing')
    parser.add_argument('--no-ssl-verify', action='store_true', help='Disable SSL verification')
    parser.add_argument('--proxy', help='HTTP proxy (e.g., http://127.0.0.1:8080)')
    parser.add_argument('--timeout', type=int, default=30, help='Request timeout in seconds')
    parser.add_argument('--output-dir', default='results', help='Output directory for results')

    args = parser.parse_args()

    # Get script directory
    script_dir = Path(__file__).parent

    if args.list:
        list_requests(script_dir)
        return

    if args.all:
        requests_list = list_requests(script_dir)
        if not requests_list:
            return

        print(f"\n[*] Executing {len(requests_list)} requests...\n")
        for request_file, _ in requests_list:
            executor = RequestExecutor(request_file, args.output_dir)
            executor.execute(
                verify_ssl=not args.no_ssl_verify,
                timeout=args.timeout,
                proxy=args.proxy
            )
            print("\n" + "="*80 + "\n")
        return

    if not args.request_file:
        parser.print_help()
        print("\n[!] Please specify a request file or use --list to see available requests")
        return

    executor = RequestExecutor(args.request_file, args.output_dir)

    if args.curl:
        print("\nGenerated curl command:")
        print("="*80)
        print(executor.generate_curl_command())
        print("="*80)
    else:
        executor.execute(
            verify_ssl=not args.no_ssl_verify,
            timeout=args.timeout,
            proxy=args.proxy
        )


if __name__ == "__main__":
    main()
