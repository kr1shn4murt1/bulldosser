# Bulldosser

Distributed stress testing framework running on Azure Container Instances. Spins up containers across many Azure regions and replays a real browser request against a target. Written for authorized load and penetration testing.

> Authorized use only. Running this against a system without written permission is a crime in most countries.

New to the project? Read [GETTING_STARTED.md](./GETTING_STARTED.md) first — plain-language walkthrough, glossary, and a safe-vs-live command list.

## What it does

The tool rents small cloud computers in up to 56 Azure regions, hands each one a copy of a real browser request captured with "Copy as cURL", and asks them all to talk to the target at the same time. Because every request carries real session cookies and browser fingerprint headers, firewalls like Cloudflare usually let the traffic through depending on configuration. Useful for load testing, WAF evaluation, and resilience testing on a target that is in scope.

Tested from an Azure subscriptions with the default quota (10 cores per region, 56 regions, 560 containers total).

## Features

- Single CLI (`bulldosser.py`) for build, deploy, status, scale, cost, teardown
- Uses the Azure SDK directly, no `az` CLI dependency beyond login
- 56 verified ACI regions, deployed in parallel
- Replays the full browser request — headers, cookies, body — to defeat WAF/Cloudflare
- All settings in YAML (`config.yaml` or `config.local.yaml`), no hardcoded values
- State file (`.bulldosser_state.json`) makes operations idempotent
- `scale` activates dormant regions as needed
- Seven attack methods: slowloris, slowpost, slowread, ws_exhaust, http_flood, plus Tor variants
- Cost estimation before deploying

## Quick Start

Prerequisites: a target with written authorization, an Azure subscription, Python 3, and Docker.

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Make a local config

```bash
cp config.yaml config.local.yaml
# edit config.local.yaml and fill in:
#   azure.subscription_id
#   azure.acr_name
```

The tool prefers `config.local.yaml` when it exists. That file is gitignored so personal IDs stay out of the repo.

### 3. Capture a real browser request

Walkthrough in [requests/README.md](./requests/README.md).

Short version: open the target in Firefox or Chrome, hit F12, go to Network, do the action to test, right-click the request, Copy as cURL (bash), paste into `requests/target_request.txt` overwriting the sample.

### 4. Log in to Azure

```bash
az login
```

### 5. Build and upload the image

```bash
python3 bulldosser.py build
```

Only needed when the attack code changes.

### 6. Run

Safe commands first.

```bash
# see the price tag
python3 bulldosser.py cost

# see what would deploy, without deploying
python3 bulldosser.py deploy --dry-run

# launch containers — sends traffic at the target
python3 bulldosser.py deploy

# see how the running containers look
python3 bulldosser.py status

# change container count
python3 bulldosser.py scale --containers 200

# read container stdout
python3 bulldosser.py logs

# shut everything down — always run when done, Azure keeps billing otherwise
python3 bulldosser.py teardown
```

## CLI Commands

safe = no traffic, no (or cents of) cost. live = sends attack traffic and/or costs real money.

| Command            | Safety | Description                                                |
|--------------------|--------|------------------------------------------------------------|
| `cost`             | safe   | Prints hourly, daily, weekly cost estimate for current config |
| `deploy --dry-run` | safe   | Shows what would be deployed, without deploying            |
| `status`           | safe   | Lists running containers by region                         |
| `logs`             | safe   | Prints container stdout (`--container NAME` for one)       |
| `build`            | live   | Builds the Docker image and pushes it to ACR               |
| `deploy`           | live   | Launches containers that send traffic at the target        |
| `scale`            | live   | Changes container count (`--containers 100`)               |
| `teardown`         | live   | Deletes everything deployed. Always run when done.         |

## Attack Methods

The names below are well-known technique names, not third-party tools. Each one is a small Python script in `attack_methods/`.

| Method          | Type                 | Default Conn | Best Against                       |
|-----------------|----------------------|:------------:|------------------------------------|
| `slowpost_tor`  | Slow POST via Tor    | 1000         | WAF with IPS rules (recommended)   |
| `slowloris_tor` | Slowloris via Tor    | 200          | IP-based rate limiting             |
| `slowpost`      | Chunked POST drip    | 500          | Apache body timeout                |
| `slowloris`     | Partial HTTP headers | 500          | Apache, Nginx                      |
| `slowread`      | Slow response drain  | 20           | Servers without send timeout       |
| `ws_exhaust`    | WebSocket hold       | 500          | WebSocket servers                  |
| `http_flood`    | Full request replay  | 200          | High-volume flood                  |

Recommended: `slowpost_tor`. Async slow POST through Tor gives maximum stealth and IP diversity. Every method uses the full captured browser request (headers, cookies, body).

## WAF Bypass

Websites put a guard in front of themselves called a WAF (Web Application Firewall) — Cloudflare, Akamai, AWS WAF, etc. These guards check every visitor for things like browser fingerprint, challenge cookies, and known bot patterns.

A generic request with no cookies would be rejected on arrival. The workaround is to copy a real browser's request after it has already passed the WAF challenge, then replay that exact request from every container. The WAF sees the same session cookie and browser headers as the human who just loaded the page, so the traffic passes.

This is why `target_request.txt` matters, and why freshness matters — session cookies expire. If attacks start failing, recapture the request.

The captured request includes:

- all HTTP headers: `User-Agent`, `Accept`, `Sec-CH-UA`, `Sec-Fetch-*`
- all cookies: `cf_clearance`, session tokens, auth cookies
- `Referer`, `Origin` — exact browser values
- request body for POST methods

## Configuration

All settings live in YAML. Copy `config.yaml` to `config.local.yaml` and edit the copy. The tool prefers the local copy when present.

```yaml
azure:
  subscription_id: "00000000-0000-0000-0000-000000000000"  # Azure subscription
  acr_name: "bulldosser-acr"                                 # Container Registry name
  resource_group: "bulldosser-rg"                          # all resources go in this group

container:
  image_tag: "latest"   # which image version to run
  cpu: 1                # vCPUs per container
  memory_gb: 1.5        # RAM per container

regions:
  - name: eastus
    containers: 10    # set to 0 to skip this region
  # ... 56 regions available — list them all, set containers:0 to disable one

attack:
  curl_file: "requests/target_request.txt"  # the captured browser request
  method: "slowpost_tor"                    # attack style — see table above
  connections: 500                          # parallel connections per container
```

## Capacity and Regions

### Default account capacity

The default Azure subscription I use includes 56 deployable ACI regions, each with a 10 StandardCores quota. At 1 vCPU per container that caps out at 560 containers total.

| Metric                    | Value          |
|---------------------------|----------------|
| Deployable regions        | 56             |
| Default cores per region  | 10             |
| Max containers (default)  | 560            |
| Blocked regions           | 1 (westeurope) |

### Scale presets

| Target     | Strategy                | Regions Used | Per Region |
|------------|-------------------------|:------------:|:----------:|
| 70         | 10 regions × 7          | 10           | 7          |
| 100        | 10 regions × 10         | 10           | 10         |
| 200        | 20 regions × 10         | 20           | 10         |
| 300        | 30 regions × 10         | 30           | 10         |
| 560 (max)  | 56 regions × 10         | 56           | 10         |

### Quota increase

Request via Azure Portal → Support + Service Limits → Microsoft.ContainerInstance → StandardCores.

| Increase          | Approval Time       |
|-------------------|---------------------|
| 10 → 50 cores     | auto-approved       |
| 10 → 100 cores    | ~24 hours           |
| 10 → 200+ cores   | 1-3 business days   |

### Verified region list (56 regions)

<details>
<summary>Click to expand</summary>

North America (10): `eastus` `eastus2` `centralus` `westus` `westus2` `westus3` `northcentralus` `southcentralus` `westcentralus` `canadacentral` `canadaeast` `mexicocentral`

South America (3): `brazilsouth` `brazilsoutheast` `chilecentral`

Europe (16): `northeurope` `uksouth` `ukwest` `francecentral` `francesouth` `germanywestcentral` `germanynorth` `swedencentral` `norwayeast` `norwaywest` `switzerlandnorth` `switzerlandwest` `polandcentral` `italynorth` `spaincentral` `austriaeast` `belgiumcentral` `denmarkeast`

Middle East & Africa (6): `uaecentral` `uaenorth` `qatarcentral` `israelcentral` `southafricanorth` `southafricawest`

Asia-Pacific (13): `australiaeast` `australiasoutheast` `australiacentral` `australiacentral2` `japaneast` `japanwest` `koreacentral` `koreasouth` `southeastasia` `eastasia` `centralindia` `southindia` `westindia` `indiasouthcentral` `indonesiacentral` `malaysiawest` `newzealandnorth`

</details>

## Project Structure

```
bulldosser/
├── bulldosser.py              # single CLI (Azure SDK)
├── config.yaml                # deployment config (56 regions)
├── requirements.txt           # Python dependencies
├── attack_methods/            # attack implementations
│   ├── Dockerfile             # container image
│   ├── start.sh               # entrypoint — picks the attack method
│   ├── request_loader.py      # decodes the REQUEST_DATA env var
│   ├── slowloris.py           # direct slowloris
│   ├── slowloris_tor.py       # Tor-routed slowloris
│   ├── slowpost.py            # async slow POST (R.U.D.Y. technique)
│   ├── slowpost_tor.py        # slow POST via Tor
│   ├── slowread.py            # slow response reading
│   ├── ws_exhaust.py          # WebSocket exhaustion
│   ├── http_flood.py          # full request replay at volume
│   └── bulldosser_tor.sh      # Tor bootstrap + attack
├── requests/                  # request capture workflow
│   ├── curl2request.py        # parses "Copy as cURL" into JSON
│   ├── execute_request.py     # single request tester
│   └── target_request.txt     # pasted curl command (sample committed)
└── TODO.md                    # roadmap
```

## Cost Estimation

```bash
python3 bulldosser.py cost
```

Pricing per container (1 vCPU, 1.5 GB RAM): ~$0.0567 / hour.

| Scale          | Containers | Hourly    | Daily      | Weekly      |
|----------------|:----------:|:---------:|:----------:|:-----------:|
| Small test     | 10         | $0.57     | $13.61     | $95.26      |
| Medium         | 70         | $3.97     | $95.26     | $666.79     |
| Large          | 200        | $11.34    | $272.16    | $1,905.12   |
| Full default   | 560        | $31.75    | $762.05    | $5,334.34   |
| Quota 50/rgn   | 2,800      | $158.76   | $3,810.24  | $26,671.68  |
| Quota 100/rgn  | 5,600      | $317.52   | $7,620.48  | $53,343.36  |

Pricing: ~$0.0000135 / vCPU / sec + ~$0.0000015 / GB / sec (Azure Container Instances, Linux).

## Legal Notice

Authorized use only. This tool is for:

- penetration testing with written authorization
- load testing your own infrastructure
- security research and education
- CTF competitions

Unauthorized use violates computer fraud laws and can lead to criminal prosecution.

## Author

Bulldosser is written and maintained by [@kr1shn4murt1](https://github.com/kr1shn4murt1).

- GitHub: [github.com/kr1shn4murt1](https://github.com/kr1shn4murt1)
- Issues and feature requests: open an issue on the repository
- Pull requests welcome — keep changes focused, note roadmap items landed in `TODO.md`

A mention in reports or write-ups is appreciated but not required (MIT).

## License

Released under the [MIT License](./LICENSE). Intended for authorized security testing and research — see the Legal Notice above.
