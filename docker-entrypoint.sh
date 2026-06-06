#!/bin/bash
set -e

APP_USER="registry"
APP_UID=$(id -u 2>/dev/null || echo "0")
APP_GID=$(id -g 2>/dev/null || echo "0")
export APP_USER APP_UID APP_GID

CERT_DIR="/opt/registry-center/etc/ssl"
SIGN_CERT_DIR="/opt/registry-center/etc/sign_cert"
DATA_DIR="/opt/registry-center/data"

mkdir -p "$CERT_DIR" "$SIGN_CERT_DIR" "$DATA_DIR" /opt/registry-center/log/audit

# ---- Helper: generate certs via Python ----
run_gen_certs() {
    local dir="$1"
    local usage="$2"
    python3 -c "
import sys
sys.path.insert(0, '/opt/registry-center')
from common.cert.certificate_generator import CertificateGenerator
gen = CertificateGenerator(key_algorithm='RSA')
ok = gen.generate_certificates('${dir}', ['${usage}'])
print('Generated' if ok else 'Skipped (files already exist)')
" 2>&1
}

# ---- TLS certificate ----
if [ ! -f "$CERT_DIR/server.cer" ] || [ ! -f "$CERT_DIR/server_key.pem" ] || [ ! -f "$CERT_DIR/cert_pwd" ]; then
    echo "[entrypoint] Generating self-signed TLS certificate..."
    rm -f "$CERT_DIR/server.cer" "$CERT_DIR/server_key.pem" "$CERT_DIR/cert_pwd"
    run_gen_certs "$CERT_DIR" "serverAuth"
fi

if [ -f "$CERT_DIR/server.cer" ] && [ ! -f "$CERT_DIR/trust.cer" ]; then
    cp "$CERT_DIR/server.cer" "$CERT_DIR/trust.cer"
    chmod 600 "$CERT_DIR/trust.cer" 2>/dev/null || true
    echo "[entrypoint] Using self-signed cert as trust.cer"
fi

# ---- Signing certificate ----
if [ ! -f "$SIGN_CERT_DIR/server.cer" ] || [ ! -f "$SIGN_CERT_DIR/server_key.pem" ] || [ ! -f "$SIGN_CERT_DIR/cert_pwd" ]; then
    echo "[entrypoint] Generating self-signed signing certificate..."
    rm -f "$SIGN_CERT_DIR/server.cer" "$SIGN_CERT_DIR/server_key.pem" "$SIGN_CERT_DIR/cert_pwd"
    run_gen_certs "$SIGN_CERT_DIR" "dataSigning"
fi

# ---- Override JWK key path (the config default 'etc/sign_cert' is a directory, need .pem file) ----
export REGISTRY_JWK_PRIVATE_KEY_PATH="etc/sign_cert/server_key.pem"
export REGISTRY_JWK_PRIVATE_KEY_PASSWORD="etc/sign_cert/cert_pwd"

echo "[entrypoint] Starting Registry Center on 0.0.0.0:5000..."
exec python3 -m agent_registry.start
