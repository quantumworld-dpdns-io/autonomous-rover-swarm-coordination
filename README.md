# Autonomous Rover Swarm Coordination

> Decentralized rover swarm coordination platform using **CRDTs** for resilient operation in hostile environments.

[![CI](https://github.com/quantumworld-dpdns-io/autonomous-rover-swarm-coordination/actions/workflows/ci.yml/badge.svg)](https://github.com/quantumworld-dpdns-io/autonomous-rover-swarm-coordination/actions/workflows/ci.yml)
[![Security](https://github.com/quantumworld-dpdns-io/autonomous-rover-swarm-coordination/actions/workflows/security.yml/badge.svg)](https://github.com/quantumworld-dpdns-io/autonomous-rover-swarm-coordination/actions/workflows/security.yml)
[![Robot Framework](https://github.com/quantumworld-dpdns-io/autonomous-rover-swarm-coordination/actions/workflows/robot-framework.yml/badge.svg)](https://github.com/quantumworld-dpdns-io/autonomous-rover-swarm-coordination/actions/workflows/robot-framework.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Architecture

Every stateful component is a **CRDT (Conflict-Free Replicated Data Type)** — enabling true decentralized coordination without any central server. Rovers sync state via MQTT/gRPC mesh, merge concurrently, and converge automatically.

```
┌─────────────────────────────────────────────────────────────────┐
│                    Rover Swarm Platform                          │
├────────────┬──────────┬───────────┬──────────┬─────────────────┤
│  CRDT Core │  Comm    │  Swarm    │  Data    │  Infrastructure │
│  ┌──────┐  │  ┌────┐  │  ┌─────┐  │  ┌───┐   │  ┌────────────┐│
│  │LWWReg│  │  │MQTT│  │  │Raft │  │  │Duck│   │  │ FastAPI    ││
│  │GCntr │  │  │gRPC│  │  │Task │  │  │Arrow│  │  │ WebSocket  ││
│  │OrSet │  │  │mDNS│  │  │Form │  │  │Ice- │  │  │ Prometheus ││
│  │LWWMap│  │  │WS  │  │  │Goss │  │  │berg │  │  │ OTel       ││
│  │RGA   │  │  │    │  │  │     │  │  │     │  │  │ Grafana    ││
│  └──────┘  │  └────┘  │  └─────┘  │  └───┘   │  └────────────┘│
├────────────┴──────────┴───────────┴──────────┴─────────────────┤
│  AI: Ollama | llama.cpp | vLLM | SGLang (pluggable adapter)    │
│  Vector DB: Chroma | LanceDB | Milvus | Qdrant | Weaviate     │
│  Simulation: SITL (custom) + HIL (Gazebo | Isaac Sim)         │
│  Security: mTLS | RBAC | JWT | OWASP Top 10 (Robot Framework) │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Clone
git clone https://github.com/quantumworld-dpdns-io/autonomous-rover-swarm-coordination.git
cd autonomous-rover-swarm-coordination

# Bootstrap
make dev

# Run tests
make test           # pytest unit + integration
make test-robot     # Robot Framework (requires Docker)
make test-security  # SAST + dependency scan

# Start ground station
make run CMD="ground-station"

# Run swarm simulation
make run CMD="simulate --count 5"

# Start a rover node
make run CMD="start"

# Docker
docker compose up -d
```

## Project Structure

```
src/rover_swarm/
├── crdt/              # 8 CRDT types + merge engine + serialization
├── communication/     # MQTT, gRPC, mDNS discovery, WebSocket bridge
├── swarm/             # Consensus (Raft), gossip, task allocation, formation
├── sensor/            # GPS, IMU, LiDAR, camera, fusion (Kalman filter)
├── ai/                # Ollama, llama.cpp, vLLM, SGLang adapters + router
├── vector_db/         # Chroma, LanceDB, Milvus, Qdrant, Weaviate + manager
├── security/          # mTLS, JWT, RBAC, rate limiter, audit, input validation
├── api/               # FastAPI + WebSocket (13 routers)
├── simulation/        # SITL simulator, Gazebo/Isaac Sim bridges, visualizer
├── observability/     # OpenTelemetry, Prometheus, W&B Weave
├── node.py            # Rover node (ties all modules together)
├── ground_station.py  # Ground station with API + MQTT bridge
├── config.py          # Pydantic settings (nested, env-based)
├── types.py           # 40+ core datatypes
├── constants.py       # System constants
└── exceptions.py      # 30+ custom exceptions

tests/
├── unit/              # 67 pytest unit tests
├── integration/       # 7 integration tests
└── robot/             # 10 Robot Framework test suites
    ├── unit/          # CRDT unit tests
    ├── integration/   # API, MQTT, swarm tests
    └── security/      # OWASP Top 10 (A1-A10)

.github/workflows/     # CI, Security Scan, Release, Robot Framework
ci/                    # Mosquitto, Prometheus, Grafana, OWASP ZAP, Trivy
docs/                  # Architecture, Security, API Reference, Integration
```

## CRDT Types

| Type | File | Description |
|------|------|-------------|
| `LwwReg` | `crdt/lwwreg.py` | Last-Writer-Wins Register |
| `GCounter` | `crdt/gcounter.py` | Grow-Only Counter |
| `PnCounter` | `crdt/pncounter.py` | Positive-Negative Counter |
| `GSet` | `crdt/gset.py` | Grow-Only Set |
| `OrSet` | `crdt/orset.py` | Observed-Remove Set |
| `LwwMap` | `crdt/lwwmap.py` | Last-Writer-Wins Map |
| `MvReg` | `crdt/mvreg.py` | Multi-Value Register |
| `Rga` | `crdt/rga.py` | Replicated Growable Array |
| `RoverState` | `crdt/rover_state.py` | Composite rover CRDT state |
| `SwarmState` | `crdt/swarm_state.py` | Aggregate swarm CRDT state |
| `MissionState` | `crdt/mission_state.py` | Mission CRDT state |

## Integrated Tools

From `software-tools/` knowledge base:

| Category | Tools Integrated | Module |
|----------|-----------------|--------|
| Vector Databases | Chroma, LanceDB, Milvus, Qdrant, Weaviate | `vector_db/` |
| AI Inference | Ollama, llama.cpp, vLLM, SGLang | `ai/` |
| Data Lakehouse | DuckDB, Apache Arrow, Apache DataFusion, Apache Iceberg, Trino | `sensor/pipeline.py`, `api/routers/data.py` |
| AI Observability | W&B Weave | `observability/evaluation.py` |
| Agent Protocols | Agent Skills | `ai/engine_manager.py` |
| Security | OWASP Top 10, mTLS, RBAC | `security/` |

## Security Testing (OWASP Top 10)

All OWASP Top 10 (2021) categories are tested via Robot Framework:

| Category | Test File | Description |
|----------|-----------|-------------|
| A1 Broken Access Control | `test_owasp_auth.robot` | Unauthenticated access, role escalation |
| A2 Cryptographic Failures | `test_owasp_data.robot` | Weak ciphers, key strength |
| A3 Injection | `test_owasp_injection.robot` | SQL, command, NoSQL injection |
| A4 Insecure Design | `test_owasp_config.robot` | Rate limiting, input validation |
| A5 Security Misconfiguration | `test_owasp_config.robot` | Headers, CORS, debug endpoints |
| A6 Vulnerable Components | `test_owasp_config.robot` | Dependency scanning |
| A7 Auth Failures | `test_owasp_auth.robot` | Token validation, brute force |
| A8 Data Integrity | `test_owasp_data.robot` | Tampered payloads, HMAC |
| A9 Logging Failures | `test_owasp_data.robot` | Audit log completeness |
| A10 SSRF | `test_owasp_data.robot` | URL injection, network filtering |

## License

MIT — see [LICENSE](LICENSE)

## Contributing

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) and [AGENTS.md](AGENTS.md)
