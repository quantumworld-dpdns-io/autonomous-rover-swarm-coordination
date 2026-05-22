# AGENTS.md — Rover Swarm Coordination

## Project Overview
Autonomous rover swarm coordination platform using CRDTs for decentralized coordination in hostile environments.

## Tech Stack
- **Language:** Python 3.12+
- **Build:** setuptools, uv
- **Style:** Black, Ruff, MyPy strict
- **Test:** pytest, Robot Framework
- **Security:** Bandit, Safety, OWASP ZAP, Semgrep
- **CI/CD:** GitHub Actions
- **Infra:** Docker, Docker Compose

## Project Structure
```
src/rover_swarm/
├── crdt/          # CRDT types and merge engine
├── communication/ # MQTT, gRPC, WebSocket
├── swarm/         # Coordination algorithms
├── sensor/        # Sensor abstraction and drivers
├── ai/            # AI inference engines
├── security/      # Auth, TLS, rate limiting
├── api/           # FastAPI + WebSocket
├── simulation/    # SITL + HIL simulation
├── observability/ # OpenTelemetry, Prometheus
├── config.py      # Pydantic settings
├── types.py       # Core types
├── constants.py   # System constants
└── exceptions.py  # Exception hierarchy
```

## Conventions
- Type hints everywhere (strict mypy)
- Dataclasses over dicts
- Loguru for logging
- Pydantic for config validation
- Async where IO-bound
- CRDT-first design: every stateful component is a CRDT

## Commit Style
- `chore:` for tooling, config, CI
- `feat:` for new features
- `fix:` for bug fixes
- `test:` for test additions
- `docs:` for documentation
- `security:` for security fixes
