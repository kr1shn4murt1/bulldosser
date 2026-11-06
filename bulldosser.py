#!/usr/bin/env python3
"""
Bulldosser — Distributed stress testing framework using Azure Container Instances.

Unified CLI for deploying, managing, and tearing down container-based
load tests across multiple Azure regions.

Usage:
    python3 bulldosser.py deploy   [-c config.yaml] [--dry-run]
    python3 bulldosser.py status   [-c config.yaml]
    python3 bulldosser.py scale    [-c config.yaml] --containers 100
    python3 bulldosser.py teardown [-c config.yaml]
    python3 bulldosser.py logs     [-c config.yaml] [--container NAME]
    python3 bulldosser.py cost     [-c config.yaml]
    python3 bulldosser.py build    [-c config.yaml]
"""

import argparse
import base64
import json
import sys
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import yaml
from azure.identity import DefaultAzureCredential
from azure.mgmt.containerinstance import ContainerInstanceManagementClient
from azure.mgmt.containerinstance.models import (
    ContainerGroup,
    Container,
    ContainerGroupNetworkProtocol,
    ContainerPort,
    EnvironmentVariable,
    ImageRegistryCredential,
    IpAddress,
    OperatingSystemTypes,
    ResourceRequests,
    ResourceRequirements,
)
from azure.mgmt.containerregistry import ContainerRegistryManagementClient
from azure.mgmt.resource.resources import ResourceManagementClient
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

STATE_FILE = ".bulldosser_state.json"
DEFAULT_CONFIG = "config.yaml"


def load_config(path: str) -> dict:
    p = Path(path)
    local = p.parent / (p.stem + ".local" + p.suffix)
    if local.exists():
        p = local
    elif not p.exists():
        print(f"[!] Config not found: {path} (or {local})")
        sys.exit(1)
    print(f"[*] Using config: {p}")
    with open(p) as f:
        return yaml.safe_load(f)


def load_state() -> dict:
    if Path(STATE_FILE).exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"containers": [], "deployed_at": None, "acr_image": None}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


def get_clients(subscription_id: str):
    credential = DefaultAzureCredential()
    return {
        "resource": ResourceManagementClient(credential, subscription_id),
        "aci": ContainerInstanceManagementClient(credential, subscription_id),
        "acr": ContainerRegistryManagementClient(credential, subscription_id),
    }


def ensure_resource_group(clients: dict, rg_name: str, location: str):
    clients["resource"].resource_groups.create_or_update(
        rg_name, {"location": location}
    )


def get_acr_credentials(clients: dict, cfg: dict) -> dict:
    acr_name = cfg["azure"]["acr_name"]
    rg = cfg["azure"]["resource_group"]
    creds = clients["acr"].registries.list_credentials(rg, acr_name)
    return {
        "server": f"{acr_name}.azurecr.io",
        "username": creds.username,
        "password": creds.passwords[0].value,
    }


def deploy_single_container(
    clients: dict, cfg: dict, acr_creds: dict, container_def: dict
) -> dict:
    aci = clients["aci"]
    rg = cfg["azure"]["resource_group"]
    acr_name = cfg["azure"]["acr_name"]
    image_tag = cfg["container"].get("image_tag", "latest")
    image = f"{acr_name}.azurecr.io/bulldosser:{image_tag}"

    name = container_def["name"]
    region = container_def["region"]
    env_vars = container_def.get("env", {})

    container = Container(
        name=name,
        image=image,
        resources=ResourceRequirements(
            requests=ResourceRequests(
                cpu=cfg["container"]["cpu"],
                memory_in_gb=cfg["container"]["memory_gb"],
            )
        ),
        environment_variables=[
            EnvironmentVariable(name=k, value=str(v)) for k, v in env_vars.items()
        ],
    )

    group = ContainerGroup(
        location=region,
        containers=[container],
        os_type=OperatingSystemTypes.LINUX,
        restart_policy=cfg["container"].get("restart_policy", "Always"),
        image_registry_credentials=[
            ImageRegistryCredential(
                server=acr_creds["server"],
                username=acr_creds["username"],
                password=acr_creds["password"],
            )
        ],
    )

    try:
        aci.container_groups.begin_create_or_update(rg, name, group)
        return {"name": name, "region": region, "status": "deploying"}
    except HttpResponseError as e:
        return {"name": name, "region": region, "status": "failed", "error": str(e)}


def _parse_curl_file(curl_path: str) -> str:
    sys.path.insert(0, str(Path(__file__).parent / "requests"))
    from curl2request import parse_curl
    with open(curl_path) as f:
        text = f.read()
    parsed = parse_curl(text)
    return base64.b64encode(json.dumps(parsed).encode()).decode()


def cmd_deploy(cfg: dict, dry_run: bool = False):
    print("\n" + "=" * 60)
    print("  BULLDOSSER — DEPLOY")
    print("=" * 60)

    regions = [r for r in cfg["regions"] if r.get("containers", 0) > 0]
    total = sum(r["containers"] for r in regions)
    attack_cfg = cfg.get("attack", {})
    method = attack_cfg.get("method", "slowpost_tor")
    connections = str(attack_cfg.get("connections", 500))

    curl_file = attack_cfg.get("curl_file", "")
    request_data_b64 = ""
    if curl_file:
        curl_path = Path(curl_file)
        if not curl_path.exists():
            curl_path = Path(__file__).parent / curl_file
        if curl_path.exists():
            request_data_b64 = _parse_curl_file(str(curl_path))
            print(f"  Curl file:  {curl_file} ({len(request_data_b64)} bytes encoded)")
        else:
            print(f"  [!] Curl file not found: {curl_file}")
            print(f"      Containers will use fallback generic headers")

    print(f"  Regions:    {len(regions)}")
    print(f"  Containers: {total}")
    print(f"  Attack:     {method}")
    print(f"  Connections:{connections}/container")
    print(f"  CPU/Mem:    {cfg['container']['cpu']} vCPU / {cfg['container']['memory_gb']} GB")
    print("=" * 60)

    REGION_PREFIX = {
        # North America (9)
        "eastus": "eu1", "eastus2": "eu2", "centralus": "cus",
        "westus": "wu1", "westus2": "wu2", "westus3": "wu3",
        "northcentralus": "ncu", "southcentralus": "scu", "westcentralus": "wcu",
        "canadacentral": "cac", "canadaeast": "cae", "mexicocentral": "mxc",
        # South America (3)
        "brazilsouth": "brs", "brazilsoutheast": "bre", "chilecentral": "clc",
        # Europe (16)
        "northeurope": "neu", "uksouth": "uks", "ukwest": "ukw",
        "francecentral": "frc", "francesouth": "frs",
        "germanywestcentral": "gwc", "germanynorth": "gen",
        "swedencentral": "swc", "norwayeast": "noe", "norwaywest": "now",
        "switzerlandnorth": "szn", "switzerlandwest": "szw",
        "polandcentral": "plc", "italynorth": "itn",
        "spaincentral": "esc", "austriaeast": "ate",
        "belgiumcentral": "bec", "denmarkeast": "dke",
        # Middle East & Africa (5)
        "uaecentral": "uac", "uaenorth": "uan",
        "qatarcentral": "qtc", "israelcentral": "ilc",
        "southafricanorth": "san", "southafricawest": "saw",
        # Asia-Pacific (13)
        "australiaeast": "aue", "australiasoutheast": "aus",
        "australiacentral": "auc", "australiacentral2": "ac2",
        "japaneast": "jpe", "japanwest": "jpw",
        "koreacentral": "krc", "koreasouth": "krs",
        "southeastasia": "sea", "eastasia": "eaa",
        "centralindia": "cin", "southindia": "sin", "westindia": "win",
        "indiasouthcentral": "isc",
        "indonesiacentral": "idc", "malaysiawest": "myw",
        "newzealandnorth": "nzn",
    }

    container_defs = []
    counter = 0

    for region_cfg in regions:
        region = region_cfg["name"]
        count = region_cfg["containers"]
        prefix = REGION_PREFIX.get(region, region[:3])

        for i in range(count):
            name = f"bull-{prefix}-{i + 1:03d}"
            env = {
                "CONTAINER_NAME": name,
                "CONTAINER_ID": str(counter + 1),
                "ATTACK_METHOD": method,
                "CONNECTIONS": connections,
                "REQUESTS_PER_CYCLE": str(attack_cfg.get("requests_per_cycle", 10000)),
                "PARALLEL_WORKERS": str(attack_cfg.get("parallel_workers", 200)),
                "SLEEP_INTERVAL": str(attack_cfg.get("sleep_interval", 5)),
            }
            if request_data_b64:
                env["REQUEST_DATA"] = request_data_b64

            container_defs.append({"name": name, "region": region, "env": env})
            counter += 1

    if dry_run:
        print(f"\n[DRY RUN] Would deploy {len(container_defs)} containers:")
        for r in regions:
            region_containers = [c for c in container_defs if c["region"] == r["name"]]
            print(f"  {r['name']}: {len(region_containers)} containers")

        hourly = _estimate_cost(cfg, total)
        print(f"\n  Estimated cost: ${hourly:.2f}/hour (${hourly * 24:.2f}/day)")
        return

    clients = get_clients(cfg["azure"]["subscription_id"])
    acr_creds = get_acr_credentials(clients, cfg)

    first_region = regions[0]["name"]
    print(f"\n[*] Ensuring resource group '{cfg['azure']['resource_group']}' exists...")
    ensure_resource_group(clients, cfg["azure"]["resource_group"], first_region)

    print(f"[*] Deploying {len(container_defs)} containers across {len(regions)} regions...\n")

    deployed = []
    failed = 0

    workers = min(50, max(20, len(container_defs) // 3))
    print(f"[*] Using {workers} parallel threads\n")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(deploy_single_container, clients, cfg, acr_creds, cdef): cdef
            for cdef in container_defs
        }
        for future in as_completed(futures):
            result = future.result()
            if result["status"] == "deploying":
                deployed.append(result)
                print(f"  [+] {result['name']} ({result['region']})")
            else:
                failed += 1
                print(f"  [!] {result['name']} FAILED: {result.get('error', 'unknown')}")

    state = load_state()
    state["containers"] = deployed
    state["deployed_at"] = datetime.now(timezone.utc).isoformat()
    state["acr_image"] = f"{cfg['azure']['acr_name']}.azurecr.io/bulldosser:{cfg['container'].get('image_tag', 'latest')}"
    state["config"] = {
        "resource_group": cfg["azure"]["resource_group"],
        "subscription_id": cfg["azure"]["subscription_id"],
    }
    save_state(state)

    print(f"\n[+] Deployed: {len(deployed)} | Failed: {failed}")
    hourly = _estimate_cost(cfg, len(deployed))
    print(f"[+] Cost: ~${hourly:.2f}/hour (${hourly * 24:.2f}/day)")
    print(f"[*] State saved to {STATE_FILE}")


def cmd_status(cfg: dict):
    print("\n" + "=" * 60)
    print("  BULLDOSSER — STATUS")
    print("=" * 60)

    clients = get_clients(cfg["azure"]["subscription_id"])
    aci = clients["aci"]
    rg = cfg["azure"]["resource_group"]

    try:
        groups = list(aci.container_groups.list_by_resource_group(rg))
    except ResourceNotFoundError:
        print(f"[!] Resource group '{rg}' not found")
        return

    if not groups:
        print("[*] No containers found")
        return

    by_region = {}
    for g in groups:
        loc = g.location
        state = "unknown"
        if g.instance_view and g.instance_view.state:
            state = g.instance_view.state
        elif g.provisioning_state:
            state = g.provisioning_state

        by_region.setdefault(loc, []).append({"name": g.name, "state": state})

    running = 0
    other = 0
    print(f"\n{'Region':<22} {'Running':>8} {'Other':>8}")
    print("-" * 40)
    for region, containers in sorted(by_region.items()):
        r = sum(1 for c in containers if c["state"].lower() == "running")
        o = len(containers) - r
        running += r
        other += o
        print(f"{region:<22} {r:>8} {o:>8}")

    print("-" * 40)
    print(f"{'TOTAL':<22} {running:>8} {other:>8}")
    print(f"\nTotal containers: {running + other}")

    hourly = _estimate_cost(cfg, running)
    print(f"Running cost: ~${hourly:.2f}/hour")


def cmd_teardown(cfg: dict):
    print("\n" + "=" * 60)
    print("  BULLDOSSER — TEARDOWN")
    print("=" * 60)

    clients = get_clients(cfg["azure"]["subscription_id"])
    aci = clients["aci"]
    rg = cfg["azure"]["resource_group"]

    try:
        groups = list(aci.container_groups.list_by_resource_group(rg))
    except ResourceNotFoundError:
        print(f"[!] Resource group '{rg}' not found")
        return

    if not groups:
        print("[*] No containers to delete")
        return

    print(f"\n[!] This will delete {len(groups)} containers in '{rg}'")
    confirm = input("Type 'yes' to confirm: ").strip()
    if confirm != "yes":
        print("Aborted.")
        return

    deleted = 0
    workers = min(50, max(20, len(groups) // 3))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(aci.container_groups.begin_delete, rg, g.name): g.name
            for g in groups
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                future.result()
                deleted += 1
                print(f"  [-] Deleted {name}")
            except Exception as e:
                print(f"  [!] Failed to delete {name}: {e}")

    print(f"\n[+] Deleted {deleted}/{len(groups)} containers")

    state = load_state()
    state["containers"] = []
    state["torn_down_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state)


def cmd_logs(cfg: dict, container_name: str = None):
    clients = get_clients(cfg["azure"]["subscription_id"])
    aci = clients["aci"]
    rg = cfg["azure"]["resource_group"]

    if container_name:
        names = [container_name]
    else:
        state = load_state()
        if state["containers"]:
            names = [c["name"] for c in state["containers"][:3]]
        else:
            try:
                groups = list(aci.container_groups.list_by_resource_group(rg))
                names = [g.name for g in groups[:3]]
            except ResourceNotFoundError:
                print("[!] No containers found")
                return

    for name in names:
        print(f"\n{'=' * 60}")
        print(f"  Logs: {name}")
        print(f"{'=' * 60}")
        try:
            logs = aci.containers.list_logs(rg, name, name)
            print(logs.content[-2000:] if len(logs.content) > 2000 else logs.content)
        except Exception as e:
            print(f"[!] Could not fetch logs: {e}")


def cmd_cost(cfg: dict):
    print("\n" + "=" * 60)
    print("  BULLDOSSER — COST ESTIMATE")
    print("=" * 60)

    regions = cfg["regions"]
    total = sum(r["containers"] for r in regions)
    cpu = cfg["container"]["cpu"]
    mem = cfg["container"]["memory_gb"]

    cpu_rate = 0.0000135
    mem_rate = 0.0000015

    per_container_sec = (cpu * cpu_rate) + (mem * mem_rate)
    per_container_hr = per_container_sec * 3600

    hourly = per_container_hr * total
    daily = hourly * 24
    weekly = daily * 7

    print(f"\n  Containers:    {total}")
    print(f"  Spec:          {cpu} vCPU / {mem} GB RAM")
    print(f"  Per container: ${per_container_hr:.4f}/hour")
    print(f"\n  {'Duration':<16} {'Cost':>12}")
    print(f"  {'-' * 28}")
    print(f"  {'1 hour':<16} ${hourly:>10.2f}")
    print(f"  {'1 day':<16} ${daily:>10.2f}")
    print(f"  {'1 week':<16} ${weekly:>10.2f}")

    for r in regions:
        region_cost = per_container_hr * r["containers"]
        print(f"\n  {r['name']}: {r['containers']} containers (${region_cost:.2f}/hr)")


def cmd_build(cfg: dict):
    print("\n" + "=" * 60)
    print("  BULLDOSSER — BUILD & PUSH IMAGE")
    print("=" * 60)

    acr_name = cfg["azure"]["acr_name"]
    rg = cfg["azure"]["resource_group"]
    tag = cfg["container"].get("image_tag", "latest")

    clients = get_clients(cfg["azure"]["subscription_id"])

    print(f"\n[*] Ensuring ACR '{acr_name}' exists...")
    try:
        clients["acr"].registries.get(rg, acr_name)
        print(f"[+] ACR '{acr_name}' found")
    except ResourceNotFoundError:
        print(f"[*] Creating ACR '{acr_name}'...")
        from azure.mgmt.containerregistry.models import Registry, Sku
        clients["acr"].registries.begin_create(
            rg,
            acr_name,
            Registry(
                location=cfg["regions"][0]["name"],
                sku=Sku(name="Basic"),
                admin_user_enabled=True,
            ),
        ).result()
        print(f"[+] ACR '{acr_name}' created")

    print(f"\n[*] Building image via ACR Build Task...")
    print(f"    Image: {acr_name}.azurecr.io/bulldosser:{tag}")
    print(f"    Context: ./attack_methods/")

    import subprocess

    result = subprocess.run(
        [
            "az", "acr", "build",
            "--registry", acr_name,
            "--image", f"bulldosser:{tag}",
            "--file", "attack_methods/Dockerfile",
            "attack_methods/",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print(f"[+] Image built and pushed: {acr_name}.azurecr.io/bulldosser:{tag}")
    else:
        print(f"[!] Build failed:\n{result.stderr[-500:]}")
        sys.exit(1)


def cmd_scale(cfg: dict, new_count: int):
    print(f"\n[*] Scaling to {new_count} containers total...")

    active_regions = [r for r in cfg["regions"] if r.get("containers", 0) > 0]
    all_regions = cfg["regions"]

    if not active_regions:
        active_regions = all_regions

    total_current = sum(r["containers"] for r in active_regions)

    if new_count > total_current and len(active_regions) < len(all_regions):
        per_region = new_count // len(all_regions)
        remainder = new_count % len(all_regions)
        for i, r in enumerate(all_regions):
            r["containers"] = per_region + (1 if i < remainder else 0)
        active_regions = all_regions
    else:
        ratio = new_count / total_current if total_current > 0 else 1
        for r in active_regions:
            r["containers"] = max(1, round(r["containers"] * ratio))

    actual = sum(r["containers"] for r in cfg["regions"])
    print(f"[*] Adjusted distribution ({actual} containers across {sum(1 for r in cfg['regions'] if r['containers'] > 0)} regions):")
    for r in cfg["regions"]:
        if r["containers"] > 0:
            print(f"    {r['name']}: {r['containers']}")

    cmd_deploy(cfg)


def _estimate_cost(cfg: dict, container_count: int) -> float:
    cpu = cfg["container"]["cpu"]
    mem = cfg["container"]["memory_gb"]
    per_sec = (cpu * 0.0000135) + (mem * 0.0000015)
    return per_sec * 3600 * container_count


def main():
    parser = argparse.ArgumentParser(
        description="Bulldosser — Distributed stress testing via Azure ACI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-c", "--config", default=DEFAULT_CONFIG, help="Config file (default: config.yaml)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_deploy = sub.add_parser("deploy", help="Deploy containers to Azure")
    p_deploy.add_argument("--dry-run", action="store_true", help="Show plan without deploying")

    sub.add_parser("status", help="Show container status across regions")
    sub.add_parser("teardown", help="Delete all deployed containers")

    p_logs = sub.add_parser("logs", help="View container logs")
    p_logs.add_argument("--container", help="Specific container name")

    sub.add_parser("cost", help="Show cost estimate")
    sub.add_parser("build", help="Build and push Docker image to ACR")

    p_scale = sub.add_parser("scale", help="Scale container count")
    p_scale.add_argument("--containers", type=int, required=True, help="Target container count")

    args = parser.parse_args()
    cfg = load_config(args.config)

    if args.command == "deploy":
        cmd_deploy(cfg, dry_run=args.dry_run)
    elif args.command == "status":
        cmd_status(cfg)
    elif args.command == "teardown":
        cmd_teardown(cfg)
    elif args.command == "logs":
        cmd_logs(cfg, container_name=args.container)
    elif args.command == "cost":
        cmd_cost(cfg)
    elif args.command == "build":
        cmd_build(cfg)
    elif args.command == "scale":
        cmd_scale(cfg, args.containers)


if __name__ == "__main__":
    main()
