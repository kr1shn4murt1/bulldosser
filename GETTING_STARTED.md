# Getting Started

Plain-language on-ramp for anyone who has not done cloud pentesting before. Read it end-to-end before running any command.

> This tool sends high volumes of traffic at a target. Only run it against a system with written permission to test. Running it against anything else is a crime in most countries. If a target is unclear, do not continue until written authorization is confirmed.

## What this is

A distributed stress-testing tool. It rents small cloud computers (Azure containers), gives each one a copy of a real browser request captured with "Copy as cURL", and asks them all to talk to one target at the same time. Because every request looks like a legitimate logged-in browser, firewalls like Cloudflare usually pass the traffic through.

Think of it as hiring 500 lookalike visitors from 56 countries and sending them to the same door at once — with written permission from the owner.

## Glossary

Short glossary for someone new to cloud or DDoS terminology.

| Term | Plain explanation |
|---|---|
| Azure | Microsoft's cloud. Small computers rented by the minute. |
| ACR (Azure Container Registry) | A storage place in Azure that holds the prepared Docker image. |
| ACI (Azure Container Instances) | The small cloud computers that actually run the test. |
| Container | One isolated mini-computer in the cloud. Disposable. |
| Region | A city or country with an Azure data center (e.g. `eastus`, `brazilsouth`). More regions, more diverse origin IPs. |
| Docker image | A frozen snapshot of code and settings. Built once, used by every container. |
| cURL | A command that sends a web request from the terminal. "Copy as cURL" exports a browser request so it can be replayed exactly. |
| WAF (Web Application Firewall) | A guard in front of a website (Cloudflare, Akamai, AWS WAF) that blocks suspicious traffic. |
| Tor | A network that hides the origin IP by bouncing traffic through volunteer relays. Used so the WAF sees thousands of different IPs. |
| Slowloris / SlowPOST / SlowRead | Attack styles that keep connections open very slowly instead of flooding. Effective against servers that do not close idle connections. |
| Quota | Azure's limit on how many containers may run at once. Default: 10 cores per region. |
| Resource Group | A folder in Azure that holds everything created by the tool, so `teardown` can delete it all at once. |
| `config.local.yaml` | Personal settings file. Not committed. Holds Azure IDs. |
| `target_request.txt` | The captured browser request that gets replayed. Overwrite the sample with a real capture before running. |

## Safe commands (no traffic, no or cents of cost)

These do not send traffic and do not cost real money. Good for learning the tool.

| Task | Command |
|---|---|
| Estimate cost | `python3 bulldosser.py cost` |
| Preview a deploy | `python3 bulldosser.py deploy --dry-run` |
| Check status | `python3 bulldosser.py status` |
| Read container stdout | `python3 bulldosser.py logs` |
| Capture a browser request | DevTools → Network → right-click → Copy as cURL (bash) → paste into `requests/target_request.txt` |
| Fill in config | Copy `config.yaml` → `config.local.yaml`, edit Azure IDs |

## Live commands (spend money, send traffic)

| Command | What it does |
|---|---|
| `python3 bulldosser.py build` | Builds and uploads the Docker image to Azure (pennies, not free) |
| `python3 bulldosser.py deploy` | Starts sending traffic at the target. Only with authorization. |
| `python3 bulldosser.py scale --containers N` | Launches more attackers. Costs grow fast. |
| `python3 bulldosser.py teardown` | Shuts everything down. Always run when the test is over. |

Rule of thumb: commands whose name is a verb that *does* something (`deploy`, `scale`, `build`, `teardown`) cost money or send traffic. Commands that just *show* something (`cost`, `status`, `logs`, `--dry-run`) do not.

## First-run checklist

1. [ ] Read this whole page, including the glossary
2. [ ] Read the Legal Notice at the bottom of `README.md` and the top of `requests/README.md`
3. [ ] Confirm the target has written authorization. Do not continue without it.
4. [ ] Install Python dependencies: `pip install -r requirements.txt`
5. [ ] Open `requests/target_request.txt` and read the sample to recognize the format
6. [ ] Run `python3 bulldosser.py cost` to see what a test would cost
7. [ ] Run `python3 bulldosser.py deploy --dry-run` to see what a deploy would do
8. [ ] For a live test: capture the browser request, run `deploy`, keep notes, monitor `status` and `logs`, then `teardown`

## If something goes wrong

- Ran a command without being sure what it did → stop, check `status`, run `teardown` if containers are deployed.
- Errors like `AuthenticationFailed` or `SubscriptionNotFound` → run `az login` again. Check `config.local.yaml` subscription ID.
- The target website looks broken after the test → normal, partly the point. Run `python3 bulldosser.py teardown`.
- Email or call from Azure about abuse → stop, teardown, check the authorization scope. Do not reply until the scope is confirmed.

## Where to look next

- `README.md` — full technical reference
- `requests/README.md` — how to capture the browser request
- `TODO.md` — roadmap
- `attack_methods/` — the actual code of each attack style
