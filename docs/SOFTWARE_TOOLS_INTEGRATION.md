# Software Tools Integration Map

This document maps the 24 tools documented in `~/Desktop/software-tools/` into the rover-swarm-coordination codebase. Each tool is assigned to a development phase and linked to the specific module where it will be integrated.

---

## Agent Protocols & Integrations

**Agent Skills** (Phase 6 — `src/rover_swarm/swarm/`)  
Agent Skills are modular capability packages that let LLM-driven agents perform tasks like file editing, web search, and database queries. In the rover project, each rover role defined in `src/rover_swarm/types.py:RoverRole` (SCOUT, TRANSPORTER, RELAY, CHARGER, GENERAL) will be backed by a set of skills loaded from a capability registry in `swarm/skills/`. For example, a SCOUT rover's skills would include terrain classification and hazard detection, while a RELAY rover would carry communication-relay and data-forwarding skills. The skills system will expose a unified interface (`def execute(skill_name: str, params: dict) -> Any`) that the swarm coordinator calls during task allocation.

**Desktop Extensions DXT** (Deployment Packaging — `src/rover_swarm/api/` and `ci/`)  
DXT is a one-click distribution format for local MCP servers. In this project, DXT will be used to package the rover's local HTTP and WebSocket API (`src/rover_swarm/api/`) as a distributable desktop extension for operators running the rover control dashboard on their local machine. The CI pipeline (`.github/workflows/`) will build a DXT bundle from the FastAPI application defined in the `web` optional dependency group.

---

## AI Agents & Coding Assistants

**Claude Code, Devin, Claude Desktop, Codex Desktop, Hermes Agent** (Development Workflow — `pyproject.toml`, `ci/`, `AGENTS.md`)  
These five AI coding agents are integrated at the development workflow layer, not the application layer. `AGENTS.md` provides the interface contract that any AI agent reads before modifying the codebase. The `pyproject.toml` defines optional dependency groups (e.g., `[project.optional-dependencies]`) that these agents install depending on which subsystem they are working on. CI/CD workflows in `.github/workflows/` include agent-invocation hooks: when an agent pushes changes, the pipeline runs lint (ruff), type-check (mypy), security scan (bandit, semgrep), and test (pytest) steps that guard against regressions. The `Makefile` wraps common agent tasks (`make lint`, `make test`, `make security`) so any AI agent can operate without knowing the raw toolchain.

---

## AI Evaluation & Observability

**W&B Weave** (Phase 7 — `src/rover_swarm/observability/`)  
W&B Weave provides LLM observability, evaluation, and prompt iteration tracking. In the rover project, Weave will trace every call made through the AI inference adapter in `src/rover_swarm/ai/` — recording model inputs, outputs, latency, and token usage. The `observability` optional dependency group in `pyproject.toml` already lists `weave>=0.3`. During Phase 7, `observability/llm_eval.py` will define evaluation pipelines that compare LLM-generated swarm decisions (e.g., route planning, task prioritisation) against ground-truth simulations, surfacing regressions in a Weave dashboard.

---

## Local AI & Model Serving

**Ollama, llama.cpp, vLLM, SGLang, LM Studio** (Phase 6 — `src/rover_swarm/ai/`)  
These five inference engines form a pluggable backend layer inside `src/rover_swarm/ai/`. The `AiConfig` class in `src/rover_swarm/config.py` already carries configuration for Ollama, vLLM, llama.cpp, and SGLang. An `InferenceEngine` abstract base class in `ai/engine.py` will define the interface (`generate()`, `embed()`, `chat()`), with concrete adapters for each engine. The `active_engine` field in `AiConfig` selects which backend to use at runtime. LM Studio will be added as a fifth adapter for operator workstations that want a GUI-driven model manager. Each adapter translates the engine-specific API (Ollama's REST API, llama.cpp's Python bindings, vLLM's OpenAI-compatible server, SGLang's structured generation endpoints) into the rover's uniform interface.

---

## Vector Databases & Retrieval

**Chroma, LanceDB, Milvus, Qdrant, Weaviate** (Phase 5 — `src/rover_swarm/security/` and `src/rover_swarm/swarm/`)  
These five vector databases form a pluggable vector DB backend behind a unified `VectorStore` abstract class in `swarm/retrieval.py`. The `VectorDbConfig` in `config.py` already holds connection settings for Chroma, Milvus, Qdrant, and Weaviate; the `vector-db` optional dependency group lists all five clients. Concrete adapters (`ChromaStore`, `LanceDbStore`, `MilvusStore`, `QdrantStore`, `WeaviateStore`) will implement `store_embedding()`, `search()`, and `delete()` operations. The primary use case is semantic retrieval of past mission telemetry: given a rover's current sensor snapshot, the swarm coordinator queries the vector DB for similar historical situations and uses the retrieved context to inform the AI model's next decision. The `active_backend` config field switches between databases at deployment time.

---

## Data Lakehouse & Query Engines

**Apache Arrow** (Phase 4 — `src/rover_swarm/sensor/`)  
Arrow's in-memory columnar format will be the standard interchange format for sensor data. The `sensor/fusion.py` module will read raw sensor readings (GPS, IMU, LIDAR, camera) as Arrow RecordBatches, enabling zero-copy sharing between the sensor fusion pipeline, the telemetry publisher, and the on-rover analytics engine. The `data` dependency group includes `pyarrow>=15.0`.

**Apache DataFusion** (Phase 4 — `src/rover_swarm/data/`)  
DataFusion's Rust-based query engine will be wrapped via its Python bindings to power distributed queries across the swarm. A `data/distributed_query.py` module will fragment SQL queries across rover nodes, push down predicates to individual rovers, and merge results through a DataFusion execution plan. This is distinct from Trino — DataFusion runs in-process on each rover for sub-second analytical queries over local Arrow data.

**Apache Iceberg** (Phase 4 — `src/rover_swarm/data/`)  
Iceberg's open table format will back the telemetry lakehouse. Every rover continuously writes telemetry packets (position, battery, speed, sensor readings) into an Iceberg table stored on S3-compatible object storage. The `DataConfig` class already has `iceberg_warehouse` and `iceberg_catalog_uri` fields. The `data/iceberg_writer.py` module will manage schema evolution, partition pruning (by `mission_id` and `hour`), and time-travel queries for post-mission analysis.

**DuckDB** (Phase 4 — `src/rover_swarm/data/`)  
DuckDB is the embedded analytical engine for on-rover SQL queries. A rover can run `SELECT AVG(battery_level), MIN(speed) FROM telemetry WHERE mission_id = ?` directly on local Arrow or Parquet files without network calls. The `data/duckdb_analytics.py` module will expose a `RoverAnalytics` class that wraps DuckDB, registers Arrow tables as views, and returns results as Arrow RecordBatches for immediate downstream consumption.

**Trino** (Phase 4 — `src/rover_swarm/data/`)  
Trino provides federated cross-rover queries. When the mission commander needs to join telemetry from all rovers with the Iceberg catalog's metadata, a Trino cluster federates across the individual rover DuckDB instances and the central Iceberg warehouse. The `data/trino_federator.py` module will register each rover as a Trino data source and expose a single SQL endpoint for the operator dashboard.

---

## Cloud-Native & Security

**KawaiiGPT** (Phase 8 — `src/rover_swarm/security/`)  
KawaiiGPT is a security awareness briefing about the risks of unapproved "shadow AI" tools that bypass enterprise security controls. In the rover project, this translates to a `security/shadow_ai_detector.py` module that monitors outbound network connections from the rover's AI inference adapters, flags unapproved model endpoints, and enforces a whitelist of allowed engines (those registered in `AiConfig`). A `security/policies/shadow_ai.yml` policy file will codify which model providers are permitted in each deployment environment (development, field trial, production).
