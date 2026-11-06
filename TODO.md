# Bulldosser — TODO

Roadmap.

- High Priority: wanted soon
- Medium Priority: useful, no fixed timeline
- Low Priority: nice-to-have

New to the project? Start with `GETTING_STARTED.md`, not this file.

## High Priority

### 1. AWS API Gateway IP rotation

Integrate `requests-ip-rotator` for 1000+ unique IPs at ~$3.50 / 1M requests.

- [ ] Install: `pip install requests-ip-rotator`
- [ ] Add `aws_gateway.py` to deploy/teardown AWS API Gateways
- [ ] Wire into `bulldosser.py` as `--provider aws`
- [ ] Test IP rotation effectiveness
- [ ] Document hybrid approach (AWS Gateway + Azure ACI)


### 2. Clean up runtime pip install in slowpost_tor

`slowpost_tor.py` falls back to installing `python-socks` at runtime if the import fails. Redundant — the Dockerfile already installs it. Remove the subprocess call.

## Medium Priority

### 2. Azure quota increase

Scale from 70 to 700 containers by requesting 100 vCPU per region.

- [ ] Azure Portal → Quotas → Container Instances
- [ ] Request 100 vCPU per region
- [ ] Redeploy with updated `config.yaml`

### 3. HTTP/2 attack vectors

Add HTTP/2 Rapid Reset (CVE-2023-44487) and stream flood.

- [ ] `attack_methods/http2_rapid_reset.py`
- [ ] `attack_methods/http2_stream_flood.py`
- [ ] Add `http2_reset` and `http2_flood` to entrypoint

## Low Priority

### 4. Monitoring dashboard

Real-time dashboard with container status, target response times, cost.

- [ ] `monitoring/dashboard.py` web UI
- [ ] Container status aggregation
- [ ] Cost tracking per hour

### 5. Multi-cloud expansion

Support AWS ECS/Fargate, GCP Cloud Run, DigitalOcean.

- [ ] Abstract provider interface in `bulldosser.py`
- [ ] AWS ECS provider
- [ ] GCP Cloud Run provider
