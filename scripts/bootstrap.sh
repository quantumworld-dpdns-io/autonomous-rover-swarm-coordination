#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "=== Rover Swarm Bootstrap ==="
echo "Project dir: $PROJECT_DIR"

# Check Python
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $PYTHON_VERSION"
if [[ "$(echo "$PYTHON_VERSION" | cut -d. -f1)" -lt 3 ]] || [[ "$(echo "$PYTHON_VERSION" | cut -d. -f2)" -lt 12 ]]; then
    echo "ERROR: Python 3.12+ required"
    exit 1
fi

# Install uv if not present
if ! command -v uv &>/dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

# Install project with all extras
echo "Installing project with all extras..."
uv pip install -e ".[all,dev,security,robot]"

# Install pre-commit hooks
echo "Installing pre-commit hooks..."
pre-commit install

# Create data directories
mkdir -p data models certs reports logs

# Generate dev certificates if not present
if [ ! -f certs/ca.crt ]; then
    echo "Generating development certificates..."
    scripts/gen_certs.sh
fi

# Create .env from example if not present
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example — edit it for your setup"
fi

echo "=== Bootstrap complete ==="
echo "Run 'source .venv/bin/activate' to activate the environment"
echo "Run 'make test' to run tests"
