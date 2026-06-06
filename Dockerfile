FROM python:3.10-slim

LABEL maintainer="OpenA2A-T"
LABEL description="A2A-T AgentCard Registry Center"

WORKDIR /opt/registry-center

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data log/audit \
    && sed -i 's/\r$//' docker-entrypoint.sh 2>/dev/null || true \
    && chmod +x docker-entrypoint.sh

EXPOSE 5000

ENV REGISTRY_IP=0.0.0.0
ENV REGISTRY_PORT=5000
ENV OPENSSL_CONF=/opt/registry-center/etc/conf/custom_openssl.cnf
ENV FORWARDED_ALLOW_IPS=*

ENTRYPOINT ["./docker-entrypoint.sh"]
