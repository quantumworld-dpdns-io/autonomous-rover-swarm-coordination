.PHONY: install dev lint format typecheck test test-security coverage clean build run docker-build docker-up docker-down pre-commit version

SHELL := /bin/bash

install:
	uv pip install -e ".[all]"

dev:
	uv pip install -e ".[all,dev,security,robot]"
	pre-commit install

lint:
	ruff check src/ tests/
	black --check src/ tests/

format:
	ruff check --fix src/ tests/
	black src/ tests/

typecheck:
	mypy src/

test:
	pytest tests/unit/ tests/integration/ -v

test-e2e:
	pytest tests/e2e/ -v

test-security:
	bandit -r src/ -f json -o reports/bandit.json || true
	safety check --json > reports/safety.json 2>/dev/null || true

test-robot:
	robot --outputdir reports/robot tests/robot/

test-robot-security:
	robot --outputdir reports/robot-security tests/robot/security/

test-all: test test-security test-e2e

coverage:
	pytest --cov=src/rover_swarm --cov-report=html --cov-report=term-missing tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov reports/ dist/ build/ *.egg-info
	rm -rf .mypy_cache .ruff_cache

build:
	python -m build

run:
	python -m rover_swarm $(CMD)

docker-build:
	docker build -t rover-swarm:latest .

docker-up:
	docker compose up -d

docker-down:
	docker compose down

pre-commit:
	pre-commit run --all-files

version:
	@cat VERSION
