#!/usr/bin/env bash
set -euo pipefail

CERT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/certs"
mkdir -p "$CERT_DIR"

echo "=== Generating development certificates ==="

# CA key and cert
openssl req -x509 -new -nodes -days 365 \
    -subj "/CN=Rover Swarm Dev CA" \
    -keyout "$CERT_DIR/ca.key" \
    -out "$CERT_DIR/ca.crt"

# Server key and CSR
openssl req -new \
    -subj "/CN=rover-swarm.local" \
    -keyout "$CERT_DIR/rover.key" \
    -out "$CERT_DIR/rover.csr"

# Server cert signed by CA
openssl x509 -req -days 365 \
    -in "$CERT_DIR/rover.csr" \
    -CA "$CERT_DIR/ca.crt" \
    -CAkey "$CERT_DIR/ca.key" \
    -CAcreateserial \
    -out "$CERT_DIR/rover.crt"

rm -f "$CERT_DIR/rover.csr" "$CERT_DIR/ca.srl"
chmod 600 "$CERT_DIR"/*.key

echo "=== Certificates generated in $CERT_DIR ==="
echo "  ca.crt     - CA certificate"
echo "  ca.key     - CA private key"
echo "  rover.crt  - Rover certificate"
echo "  rover.key  - Rover private key"
