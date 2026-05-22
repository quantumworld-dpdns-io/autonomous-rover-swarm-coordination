# Security Overview: Autonomous Rover Swarm Coordination Platform

## 1. Security Architecture Overview

The rover swarm platform operates on a **zero-trust, CRDT-first security model** designed for hostile environments where network connectivity may be intermittent and adversaries may attempt to disrupt coordination. The architecture is layered with defense-in-depth principles:

- **Data Layer**: All state is stored in CRDTs (Conflict-free Replicated Data Types) with cryptographic signatures on each operation. CRDTs provide eventual consistency without requiring a central authority, making the system resilient to network partitions.

- **Communication Layer**: Mutual TLS (mTLS) is mandatory for all intra-swarm communication (MQTT, gRPC, WebSocket). Each rover possesses a unique x.509 certificate signed by a dedicated swarm CA.

- **API Layer**: FastAPI endpoints are protected with JWT authentication, RBAC authorization, and rate limiting. The WebSocket real-time channel requires both mTLS client certificate validation and JWT token verification.

- **Observability Layer**: OpenTelemetry instruments all security-sensitive operations. Security events flow to a SIEM-compatible collector with alerting for anomalies (unusual certificate access, unexpected rover reconfigurations, CRDT operations from unregistered nodes).

- **AI Inference Layer**: Model inputs are sanitized and rate-limited. Inference results are signed and verified before consumption by coordination logic.

## 2. Threat Model (STRIDE Analysis)

### Spoofing
- **Threat**: Attacker forges rover identity or API credentials.
- **Mitigation**: mTLS with rover-unique certificates; JWT with signature validation; `RoverIdentity` dataclass includes certificate fingerprint binding; all CRDT operations require node signatures.

### Tampering
- **Threat**: Adversary modifies commands, telemetry, or CRDT state in transit or at rest.
- **Mitigation**: TLS 1.3 for all communications; `MessageEnvelope` includes HMAC signatures; CRDT operations are individually signed; vector clocks prevent replay attacks; integrity checksums on persisted state.

### Repudiation
- **Threat**: Malicious rover or operator denies issuing commands.
- **Mitigation**: Immutable audit logs with cryptographically signed entries; every `MessageEnvelope` carries a signature; all state mutations in CRDTs retain actor identity; SIEM integration provides non-repudiable trails.

### Information Disclosure
- **Threat**: Eavesdropping on telemetry, commands, or sensor data; unauthorized access to mission plans.
- **Mitigation**: mTLS everywhere; JWT claims scoped to mission roles; sensor data encrypted at rest via AES-256-GCM; vector database queries require API tokens tied to RBAC roles; configuration secrets never logged.

### Denial of Service
- **Threat**: Resource exhaustion attacks against the API; MQTT message flooding; gRPC amplification.
- **Mitigation**: Per-IP and per-rover rate limiting (configurable via `RateLimitConfig`); connection pooling with max limits; MQTT QoS levels and topic ACLs; Kubernetes readiness/liveness probes; circuit breakers on external AI/vector DB calls.

### Elevation of Privilege
- **Threat**: Rover or API user gains unauthorized permissions; compromised rover attempts to reconfigure swarm.
- **Mitigation**: RBAC with role hierarchy (admin → operator → observer → rover); JWT claims include role and mission scope; CRDT merge policies enforce write permissions based on node role; configuration changes require quorum approval in secure modes.

## 3. OWASP Top 10 (2021) Mitigation Strategies

### A01: Broken Access Control
- **Mitigation**: RBAC middleware validates permissions on every endpoint; resource ownership checks (e.g., a rover can only update its own telemetry); `AuthorizationError` is raised for insufficient permissions; IDOR mitigations via UUID-based identifiers with permission checks; CORS `allow_origins` configurable via `ApiConfig.cors_origins` (never "*" in production).

### A02: Cryptographic Failures
- **Mitigation**: TLS 1.3 only (TLS 1.0/1.1/1.2 disabled by default); `cryptography` library used for all crypto operations (no custom crypto); AES-256-GCM for data at rest; ECDSA for signing; JWT uses HS256/RS256 with secret rotation; default secrets (`change-me-in-production`) trigger a `ConfigurationError` at startup; certificate paths validated in `TlsConfig`.

### A03: Injection
- **Mitigation**: Pydantic models validate all API inputs; DuckDB/vector DB queries use parameterized interfaces; orjson/msgpack for safe serialization; `node_id` validated with alphanumeric whitelist; SQLAlchemy ORM (no raw SQL); AI inference prompts sanitized and size-limited; MQTT topics validated against allowed patterns.

### A04: Insecure Design
- **Mitigation**: Security-by-default configuration (TLS enabled); fail-closed on authentication/authorization errors; Pydantic settings enforce types and bounds (e.g., port ranges 1-65535, rate limits ≥1); input validation on all external boundaries; threat-modeled design reviewed pre-implementation; CRDT operations idempotent and commutative to reduce attack surface.

### A05: Security Misconfiguration
- **Mitigation**: Immutable `Settings` class with env var only configuration; `secrets_dir=/run/secrets` for Docker secrets; `extra="ignore"` on Pydantic models to prevent unexpected fields; default `cors_origins=["*"]` logs a security warning in production; `ApiConfig.jwt_secret` minimum length 16; all default values documented as "development-only" with production hardening guides.

### A06: Vulnerable and Outdated Components
- **Mitigation**: `pyproject.toml` specifies minimum versions; `security` extra includes bandit, safety, pip-audit, semgrep; CI runs dependency scanning on every PR; pip-audit gates deployments on CRITICAL/HIGH vulnerabilities; transitive dependencies pinned via `uv.lock`; SBOM generated on release and attached to artifacts.

### A07: Identification and Authentication Failures
- **Mitigation**: JWT access tokens expire (configurable `access_token_expire_minutes`); no refresh tokens without binding to mTLS client identity; `AuthenticationError` raised on invalid/missing tokens; rate limits on authentication endpoints; credentials never logged; password-based MQTT auth (when used) requires strong passwords via policy; rover certificates have short TTL with automated rotation.

### A08: Software and Data Integrity Failures
- **Mitigation**: `MessageEnvelope` includes `signature` field; all CRDT operations signed; SBOM attestation via SLSA 3+ where possible; Docker images signed with Cosign; no unsigned package installs; `safety` and `pip-audit` check for known compromised packages; configuration changes validated by `Settings` before application; AI model integrity checked via hash comparison.

### A09: Security Logging and Monitoring Failures
- **Mitigation**: Loguru structured logging; security events (auth failures, permission denials, certificate validation errors) logged at WARNING/ERROR; OpenTelemetry traces include security context; Prometheus metrics track `authentication_failures_total`, `authorization_denials_total`, `rate_limit_hits_total`; alerts configured for threshold breaches; logs never contain secrets (filtering via Pydantic sensitive fields).

### A10: Server-Side Request Forgery
- **Mitigation**: `MqttConfig`, `GrpcConfig`, and vector DB hosts validated; no arbitrary URL fetching exposed in API; `OllamaConfig`, `VllmConfig` restrict to configured hosts; HTTP client for external calls uses allowlists; AI inference engine calls cannot be pointed at unapproved endpoints; gRPC/mqtt services never proxy arbitrary requests.

## 4. mTLS Implementation for Intra-Swarm Communication

Every rover and service endpoint uses mTLS with a private swarm PKI:

- **Certificate Authority**: A dedicated offline root CA signs intermediate CA(s) for each mission. Rovers receive end-entity certificates signed by the mission intermediate.
- **Certificate Structure**: Each certificate's SAN includes the rover's `node_id` and `rover_id` (e.g., `URI:rover://rover-01/node-7a3f9c`). This binding is verified in `security/` middleware.
- **MQTT**: When `tls_enabled=true` in `MqttConfig`, the client presents its certificate and validates the broker's cert using `ca_path`. Topic ACLs are enforced by certificate CN.
- **gRPC**: `GrpcConfig.tls_enabled` controls mTLS. Server-side `ssl` context requires client certs via `SSLContext.verify_mode = ssl.CERT_REQUIRED`.
- **WebSocket**: WebSocket endpoints for real-time telemetry require both mTLS handshake validation and a JWT in the `Authorization` header, providing two layers of authentication.
- **Rotation**: Rover certificates have 7-day TTL. A certificate renewal gRPC service allows rovers to request new certs, authenticated by their current valid certificate.

## 5. RBAC and JWT Authentication

The platform implements **RBAC over JWT** for API and inter-service access:

- **Roles**: Defined roles map to `RoverRole` and human operator roles:
  - `ADMIN`: Full configuration, mission creation, rover enrollment
  - `OPERATOR`: Mission control, task allocation, rover commands
  - `OBSERVER`: Read-only telemetry, mission status
  - `ROVER`: Limited to sending own telemetry, receiving assigned tasks
- **JWT Structure**: Claims include `sub` (subject), `role`, `mission_id`, `scope`, and `client_cert_fingerprint` (for mTLS-bound tokens).
- **Validation**: `ApiConfig.jwt_algorithm` specifies HS256 (symmetric) or RS256 (asymmetric). Tokens are validated for signature, expiry, and required claims before RBAC evaluation.
- **Middleware Flow**:
  1. Extract JWT from `Authorization: Bearer <token>`
  2. Validate signature and expiry
  3. Map `role` claim to permissions set
  4. Compare required permission for endpoint against token permissions
  5. Raise `AuthorizationError` if insufficient, `AuthenticationError` if invalid

## 6. Rate Limiting and DoS Protection

- **Layered Rate Limits**:
  - **API Layer**: `RateLimitConfig.requests_per_minute` (default 60) applied per client IP via `slowapi`/`limits`.
  - **Rover Layer**: MQTT message rate per rover enforced at broker and within `communication/mqtt_client.py`.
  - **AI Inference**: Requests to Ollama/vLLM are rate-limited per rover to prevent resource exhaustion.
- **Backpressure**: gRPC streaming and WebSocket connections use windowing and backpressure signaling. Clients exceeding buffered limits are throttled then disconnected.
- **Connection Limits**: MQTT broker configured with `max_connections`; gRPC server enforces `max_concurrent_streams`; uvicorn worker count and backlog tuned.
- **Network Partition Resilience**: CRDT design allows rovers to operate offline during DoS; state merges automatically once connectivity resumes.

## 7. Secret Management

- **Configuration Sources**: `Settings` reads secrets from:
  1. Environment variables with `ROVER_SWARM__` prefix
  2. `secrets_dir=/run/secrets` (Docker/Kubernetes secrets mounted as files)
  3. `.env` file (development only — excluded from production containers)
- **Sensitive Fields**: `MqttConfig.password`, `ApiConfig.jwt_secret`, and TLS keys are never logged. Pydantic excludes them from `repr` via `Field(exclude=True)` patterns (to be enforced).
- **Rotation**: JWT secrets can be rotated without downtime by accepting multiple valid keys during a transition window. TLS certificates are rotated via the renewal service.
- **Prohibited Defaults**: If `jwt_secret="change-me-in-production"` in production, the service logs a CRITICAL error and may exit (configurable via strict mode).

## 8. Supply Chain Security

- **SBOM Generation**: On every release, `cyclonedx-python` generates an SBOM in CycloneDX format including transitive dependencies. SBOM is signed and attached to GitHub releases.
- **Dependency Scanning**: CI pipeline runs:
  - `bandit`: Static AST-based security scanning
  - `safety`: Known vulnerability database lookup
  - `pip-audit`: PyPI advisory database check
  - `semgrep`: Rule-based security linting
- **Pin Versions**: `pyproject.toml` uses lower bounds; `uv.lock` (or `requirements.txt`) pins exact versions for deployment.
- **SLSA Compliance**: Build process is reproducible. GitHub Actions OIDC token used for signing artifacts. Container images built in isolated CI with attestations.
- **Provenance**: Docker images pushed to registry with Cosign signatures. Deployments validate signature before pull.

## 9. Incident Response Plan

### Preparation
- IR team roster maintained; quarterly tabletop exercises.
- SIEM dashboards monitor authentication failures, certificate anomalies, and unexpected role escalations.
- Playbooks exist for: compromised rover isolation, credential rotation, DoS mitigation, mission abort.

### Detection & Analysis
- Security events correlated across logs, metrics, and traces.
- Anomaly detection: A rover attempting commands outside its role scope, certificate CN mismatches, CRDT merges from unregistered `node_id`.
- Severity levels:
  - **CRITICAL**: Mission safety compromised; adversary has root on rover; swarm split-brain induced.
  - **HIGH**: Credential exposure; unauthorized API access; certificate validation bypass suspected.
  - **MEDIUM/LOW**: Policy violations; failed logins; low-severity dependency vulnerabilities.

### Containment, Eradication, Recovery
- **Containment**: For a compromised rover, the operator revokes its certificate via CRL/OCSP; swarm RBAC is updated to exclude the rover; CRDT operations from that `node_id` are ignored.
- **Eradication**: Vulnerable component updated; secrets rotated; rover re-imaged if physical access allows.
- **Recovery**: Restore from last known-good CRDT state snapshot; validate mission state integrity; gradually reintroduce rovers.
- **Post-Incident**: Retrospective within 5 business days; findings fed back to threat model and security tests.

## 10. Vulnerability Disclosure Policy

### Scope
This policy applies to vulnerabilities in the rover swarm platform code, configuration defaults, and architecture design.

### Reporting
- Security vulnerabilities should be reported via email to `security@quantumworld-dpdns-io.github.com` (or configured security contact).
- Encrypt sensitive reports using the PGP key available in `docs/SECURITY_PGP.asc`.
- Include:
  - Component and version affected
  - Steps to reproduce (PoC preferred)
  - Potential impact
  - Proposed fix (if available)

### Response Timeline
- **Acknowledgment**: Within 2 business days.
- **Triage & Validation**: Within 5 business days.
- **Fix Development**: Timeframe depends on severity (CRITICAL: target 7 days; HIGH: 14 days).
- **Coordinated Disclosure**: Reporter will be notified when a fix is available and given advance notice before public disclosure.

### Safe Harbor
- We consider vulnerability research conducted under this policy as authorized, provided it complies with law and avoids harm to rovers, missions, or data.
- We will not initiate legal action against researchers acting in good faith per this policy.

### Out of Scope
- Vulnerabilities requiring physical possession of rover hardware without proof of remote exploitability.
- Denial of service against development/test instances without demonstrated impact.
- Theoretical vulnerabilities without a plausible exploit path.

---

**Last Updated**: May 2026  
**Contact**: security@quantumworld-dpdns-io.github.com  
**PGP Fingerprint**: See `docs/SECURITY_PGP.asc`
