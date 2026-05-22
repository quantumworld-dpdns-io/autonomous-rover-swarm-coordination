#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

TAG="${1:-latest}"
PLATFORMS="${2:-linux/amd64}"

echo "=== Building rover-swarm:$TAG for $PLATFORMS ==="

docker buildx build \
    --platform "$PLATFORMS" \
    --target runtime \
    -t "rover-swarm:$TAG" \
    -f Dockerfile \
    .

echo "=== Build complete ==="
