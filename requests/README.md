# Request Capture Workflow

## Purpose

Before the attack containers can run, they need the exact request a real browser sends to the target. Every container then pretends to be that browser, and website firewalls (Cloudflare, Akamai, AWS WAF) treat the traffic as normal.

The job in this folder: capture one real browser request and save it to `target_request.txt`.

A ready-to-edit sample lives in [`target_request.txt`](./target_request.txt). It has placeholders like `<SESSION_VALUE>` and `<FORM_BUILD_ID>` — overwrite the whole file with a real captured request. The placeholders are a reference for the format.

## Steps

### 1. Capture the request

1. Open browser DevTools → Network tab
2. Navigate to the target page (ideally a POST endpoint)
3. Right-click the request → Copy as cURL (bash)
4. Paste into `requests/target_request.txt`, overwriting the sample

> On Windows the browser also offers "Copy as cURL (cmd)", which escapes characters differently (e.g. `%"5B`). Always use the (bash) variant for Linux/macOS/Git Bash compatibility and so `curl2request.py` parses it correctly.

### 2. Preview (optional)

```bash
python3 curl2request.py target_request.txt --preview
```

Shows the parsed URL, method, headers, cookies, and body.

### 3. Save as JSON (optional)

```bash
python3 curl2request.py target_request.txt -o 01_target.json
```

### 4. Test a single request (optional)

```bash
python3 execute_request.py 01_target.json
```

### 5. Deploy

Set `attack.curl_file` in the config:

```yaml
attack:
  curl_file: "requests/target_request.txt"
  method: "slowpost_tor"
```

```bash
python3 bulldosser.py deploy
```

The deploy command reads the curl file, parses it, and passes the full request as a `REQUEST_DATA` env var (base64-encoded JSON) to every container. Each attack script uses all headers and cookies from the captured request.

## What gets captured

"Copy as cURL" hands over everything the browser would send:

- all HTTP headers — `User-Agent` (which browser), `Accept` (what the browser wants back), `Sec-CH-UA` and `Sec-Fetch-*` (modern browser fingerprint)
- all cookies — `cf_clearance` (Cloudflare "challenge passed" cookie), session tokens, login cookies
- `Referer` and `Origin` — the page the browser reports it came from
- path and query string — the real URL on the target
- content type and body — the form data, for POST requests

## Why this matters

Websites run a guard in front called a WAF (Web Application Firewall) — Cloudflare, Akamai, AWS WAF, etc. These guards check every visitor for things like "is this a real browser?" and "does this cookie prove the challenge was already passed?".

A generic request gets rejected on arrival. A captured request taken after the browser has already passed the challenge looks identical to that same person loading the page a second ago, so it passes.

Freshness matters. Session cookies expire. If attacks start failing, recapture.

## Files

| File                  | Purpose |
|-----------------------|---------|
| `curl2request.py`     | Parses the curl command into JSON |
| `execute_request.py`  | Sends a single test request |
| `target_request.txt`  | Sample / pasted curl command (committed to the repo) |

## Important

The captured request includes session cookies, tokens (`form_build_id`), IPs, and whatever data was typed. Replace them with generic values (like the sample file) before committing to a public repo.
