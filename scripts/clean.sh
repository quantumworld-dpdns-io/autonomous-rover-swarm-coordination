#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "=== Cleaning project artifacts ==="

# Python cache
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete

# Build artifacts
rm -rf dist/ build/ *.egg-info .eggs

# Test artifacts
rm -rf .pytest_cache .coverage htmlcov/ reports/ coverage.xml
rm -rf .mypy_cache .ruff_cache

# Environment
rm -rf .venv

# Docker
rm -rf .docker

# Logs
rm -rf logs/ *.log

# Data
rm -rf data/

echo "=== Clean complete ==="
