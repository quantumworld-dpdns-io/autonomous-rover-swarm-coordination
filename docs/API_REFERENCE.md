# API Reference — Rover Swarm Coordination Platform

Base URL: `http://host:8080/api/v1`  
WebSocket base: `ws://host:8080/ws`  
Auth: Bearer JWT token (`Authorization: Bearer <token>`)  
Rate limit: 60 req/min per client (configurable via `RateLimitConfig`)

---

## REST Endpoints

### Swarm

#### `GET /swarm/rovers`
List all rovers in the swarm.

- **Auth:** required
- **Rate limit:** 60/min
- **Response `200`:**
```json
{
  "rovers": [
    {
      "rover_id": "rover-01",
      "node_id": "rover-01",
      "role": "scout",
      "status": "online",
      "position": { "x": 10.5, "y": 20.0, "z": 0.0 },
      "battery_level": 0.85,
      "version": "0.1.0",
      "last_seen": 1715000000.0
    }
  ],
  "count": 5
}
```

#### `GET /swarm/rovers/{rover_id}`
Get a single rover's details.

- **Auth:** required
- **Rate limit:** 60/min
- **Response `200`:** Full `RoverIdentity` + live status
- **Response `404`:** `{ "detail": "Rover not found" }`

#### `GET /swarm/status`
Swarm aggregate status including leader, partition state, and member counts.

- **Auth:** required
- **Rate limit:** 60/min
- **Response `200`:**
```json
{
  "total_rovers": 5,
  "online": 4,
  "offline": 1,
  "leader": "rover-01",
  "partitions": 1,
  "mission_active": true
}
```

#### `GET /swarm/topology`
Swarm mesh topology — peer connections and link quality.

- **Auth:** required
- **Rate limit:** 30/min
- **Response `200`:**
```json
{
  "links": [
    { "source": "rover-01", "target": "rover-02", "rssi": -65, "latency_ms": 12.3 }
  ],
  "graph": { ... }
}
```

---

### Missions

#### `POST /missions`
Create a new mission.

- **Auth:** required
- **Rate limit:** 20/min
- **Request:**
```json
{
  "name": "Zone Alpha Survey",
  "phase": "initializing",
  "target_area": { "x_min": 0, "y_min": 0, "x_max": 100, "y_max": 100 },
  "rover_ids": ["rover-01", "rover-02"],
  "payload": {}
}
```
- **Response `201`:**
```json
{
  "mission_id": "mission-uuid",
  "name": "Zone Alpha Survey",
  "phase": "initializing",
  "created_at": 1715000000.0,
  "rover_ids": ["rover-01", "rover-02"]
}
```

#### `GET /missions`
List all missions, with optional status filter.

- **Auth:** required
- **Rate limit:** 60/min
- **Query params:** `?phase=exploring&limit=10&offset=0`
- **Response `200`:** `{ "missions": [...], "total": 3 }`

#### `GET /missions/{mission_id}`
Get mission details including progress and assigned rovers.

- **Auth:** required
- **Rate limit:** 60/min
- **Response `200`:** Full mission object
- **Response `404`:** `{ "detail": "Mission not found" }`

#### `PUT /missions/{mission_id}`
Update mission parameters or phase.

- **Auth:** required
- **Rate limit:** 20/min
- **Request:** Partial mission fields
- **Response `200`:** Updated mission object

#### `DELETE /missions/{mission_id}`
Cancel and archive a mission.

- **Auth:** required (admin role)
- **Rate limit:** 10/min
- **Response `200`:**
```json
{ "mission_id": "mission-uuid", "status": "cancelled", "archived": true }
```

---

### Commands

#### `POST /rovers/{rover_id}/commands`
Send a command to a specific rover.

- **Auth:** required
- **Rate limit:** 30/min
- **Request:**
```json
{
  "command": "move_to",
  "params": { "x": 50.0, "y": 30.0, "z": 0.0 },
  "priority": 1,
  "ttl": 30.0
}
```
- **Response `202`:**
```json
{
  "command_id": "cmd-uuid",
  "rover_id": "rover-01",
  "status": "queued",
  "timestamp": 1715000000.0
}
```

#### `POST /swarm/commands`
Broadcast command to all rovers in the swarm.

- **Auth:** required (admin role)
- **Rate limit:** 10/min
- **Request:** Same shape as single-rover command
- **Response `202`:**
```json
{
  "command_id": "cmd-uuid",
  "target_rovers": ["rover-01", "rover-02", "rover-03"],
  "status": "broadcasting"
}
```

---

### Tasks

#### `GET /tasks`
List tasks with optional filters.

- **Auth:** required
- **Rate limit:** 60/min
- **Query params:** `?status=pending&task_type=explore&assigned_to=rover-01&limit=50`
- **Response `200`:**
```json
{
  "tasks": [
    {
      "task_id": "task-uuid",
      "task_type": "explore",
      "status": "in_progress",
      "assigned_to": "rover-01",
      "priority": 0,
      "payload": {},
      "created_at": 1715000000.0,
      "deadline": 1715003600.0
    }
  ],
  "total": 12
}
```

#### `POST /tasks`
Create a new task for allocation.

- **Auth:** required
- **Rate limit:** 30/min
- **Request:** `Task` fields (task_type, payload, priority, deadline)
- **Response `201`:** Created task with generated `task_id` and `status: "pending"`

#### `PUT /tasks/{task_id}`
Update task status or reassign.

- **Auth:** required
- **Rate limit:** 30/min
- **Request:**
```json
{
  "status": "in_progress",
  "assigned_to": "rover-02"
}
```
- **Response `200`:** Updated task

---

### Telemetry

#### `GET /rovers/{rover_id}/telemetry`
Get latest telemetry snapshot for a rover.

- **Auth:** required
- **Rate limit:** 60/min
- **Query params:** `?sensors=gps,imu,battery` (optional filter)
- **Response `200`:**
```json
{
  "rover_id": "rover-01",
  "position": { "x": 10.5, "y": 20.0, "z": 0.0 },
  "orientation": { "roll": 0.0, "pitch": 0.0, "yaw": 45.0 },
  "battery_level": 0.85,
  "speed": 1.2,
  "heading": 45.0,
  "status": "online",
  "timestamp": 1715000000.0,
  "sensors": { "gps": { ... }, "imu": { ... } }
}
```

#### `GET /rovers/{rover_id}/telemetry/stream`
WebSocket upgrade — stream real-time telemetry updates.

- **Auth:** required
- **Rate limit:** N/A (single persistent connection)
- **Messages:** Server pushes `TelemetryPacket` JSON every `TELEMETRY_PUBLISH_INTERVAL` (1s)

---

### Data

#### `GET /data/query`
Execute SQL query against the DuckDB/DataFusion telemetry store.

- **Auth:** required (admin role)
- **Rate limit:** 30/min
- **Query params:** `?sql=SELECT * FROM telemetry WHERE rover_id='rover-01' LIMIT 100`
- **Response `200`:**
```json
{
  "columns": ["rover_id", "timestamp", "battery_level"],
  "rows": [ ["rover-01", 1715000000.0, 0.85] ],
  "row_count": 1,
  "elapsed_ms": 2.3
}
```

#### `POST /data/export`
Export query results to Parquet.

- **Auth:** required (admin role)
- **Rate limit:** 10/min
- **Request:**
```json
{
  "sql": "SELECT * FROM telemetry WHERE timestamp > 1715000000",
  "format": "parquet",
  "destination": "/exports/telemetry_export.parquet"
}
```
- **Response `200`:**
```json
{
  "path": "/exports/telemetry_export.parquet",
  "row_count": 5000,
  "size_bytes": 256000
}
```

---

### Vector Search

#### `POST /search/vector`
Vector similarity search across all indexed embeddings.

- **Auth:** required
- **Rate limit:** 30/min
- **Request:**
```json
{
  "vector": [0.12, 0.34, 0.56, ...],
  "top_k": 10,
  "collection": "terrain_embeddings",
  "filters": { "rover_id": "rover-01" }
}
```
- **Response `200`:**
```json
{
  "results": [
    { "id": "doc-uuid", "score": 0.95, "payload": { ... } }
  ],
  "backend": "chroma",
  "elapsed_ms": 4.2
}
```

#### `POST /search/hybrid`
Hybrid search across vector, full-text, and metadata backends.

- **Auth:** required
- **Rate limit:** 30/min
- **Request:**
```json
{
  "query": "rocky terrain near north ridge",
  "vector": null,
  "top_k": 10,
  "weights": { "vector": 0.6, "text": 0.3, "metadata": 0.1 }
}
```
- **Response `200`:** Merged result set from all active backends

---

### Security

#### `POST /auth/login`
Authenticate and receive JWT tokens.

- **Auth:** none
- **Rate limit:** 10/min per IP
- **Request:**
```json
{
  "username": "operator",
  "password": "..."
}
```
- **Response `200`:**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800,
  "refresh_token": "eyJ..."
}
```

#### `POST /auth/refresh`
Refresh an expiring access token.

- **Auth:** none (uses refresh token)
- **Rate limit:** 20/min
- **Request:**
```json
{
  "refresh_token": "eyJ..."
}
```
- **Response `200`:** Same shape as login

#### `GET /auth/me`
Return current user info from the access token.

- **Auth:** required
- **Rate limit:** 60/min
- **Response `200`:**
```json
{
  "username": "operator",
  "role": "admin",
  "permissions": ["swarm:read", "swarm:write", "missions:*"]
}
```

---

### Observability

#### `GET /metrics`
Prometheus-formatted metrics endpoint.

- **Auth:** none (scraped by Prometheus)
- **Rate limit:** N/A
- **Response `200`:** `text/plain` Prometheus exposition format

#### `GET /health`
Liveness probe — returns OK if the API process is alive.

- **Auth:** none
- **Rate limit:** N/A
- **Response `200`:**
```json
{ "status": "healthy", "timestamp": 1715000000.0 }
```

#### `GET /ready`
Readiness probe — returns OK when all backends (MQTT, gRPC, vector DB, AI engine) are connected.

- **Auth:** none
- **Rate limit:** N/A
- **Response `200`:**
```json
{
  "status": "ready",
  "checks": {
    "mqtt": "ok",
    "grpc": "ok",
    "vector_db": "ok",
    "ai_engine": "ok",
    "duckdb": "ok"
  },
  "timestamp": 1715000000.0
}
```
- **Response `503`:** One or more backends unavailable

---

## WebSocket Endpoints

All WebSocket connections require the JWT token as a query parameter: `?token=eyJ...`

### `ws://host/ws/swarm`
Subscribe to real-time swarm state updates.

- **Auth:** required (query param)
- **Messages (server → client):**
```json
{
  "event": "rover_joined",
  "data": { "rover_id": "rover-06", "role": "scout" }
}
```
```json
{
  "event": "rover_left",
  "data": { "rover_id": "rover-03" }
}
```
```json
{
  "event": "topology_change",
  "data": { "links": [...] }
}
```
```json
{
  "event": "leader_elected",
  "data": { "leader": "rover-02", "term": 3 }
}
```
```json
{
  "event": "partition_detected",
  "data": { "partition_id": "net-2", "members": ["rover-04"] }
}
```

### `ws://host/ws/rovers/{rover_id}`
Subscribe to a specific rover's telemetry stream.

- **Auth:** required (query param)
- **Messages (server → client):** `TelemetryPacket` JSON at 1 Hz
```json
{
  "rover_id": "rover-01",
  "position": { "x": 10.5, "y": 20.0, "z": 0.0 },
  "orientation": { "roll": 0.0, "pitch": 0.0, "yaw": 45.0 },
  "battery_level": 0.85,
  "speed": 1.2,
  "heading": 45.0,
  "status": "online",
  "timestamp": 1715000000.0
}
```

### `ws://host/ws/alerts`
Subscribe to real-time system alerts.

- **Auth:** required (query param)
- **Messages (server → client):**
```json
{
  "event": "alert",
  "severity": "warning",
  "source": "rover-01",
  "message": "Battery below 20%",
  "timestamp": 1715000000.0,
  "payload": { "battery_level": 0.18 }
}
```
```json
{
  "event": "alert",
  "severity": "critical",
  "source": "swarm",
  "message": "Network partition detected",
  "timestamp": 1715000000.0,
  "payload": { "partitioned_rovers": ["rover-04", "rover-05"] }
}
```

---

## Error Responses

All REST endpoints return consistent error shapes:

```json
{
  "detail": "Human-readable error message",
  "code": "ROVER_NOT_FOUND",
  "request_id": "req-uuid",
  "timestamp": 1715000000.0
}
```

| HTTP Status | Meaning                  |
|-------------|--------------------------|
| 400         | Validation error         |
| 401         | Missing or invalid token |
| 403         | Insufficient permissions |
| 404         | Resource not found       |
| 429         | Rate limit exceeded      |
| 503         | Backend unavailable      |

---

## Authentication

1. Call `POST /auth/login` with credentials to receive an access token (30 min TTL) and a refresh token (7 day TTL).
2. Include `Authorization: Bearer <access_token>` in all authenticated requests.
3. When the access token expires, call `POST /auth/refresh` with the refresh token.
4. WebSocket connections pass the token as `?token=<access_token>`.

---

## Rate Limiting

Default: **60 requests per minute** per client IP.

Headers returned on every response:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 42
X-RateLimit-Reset: 1715000060
```

When exceeded:

```
Status: 429 Too Many Requests
Retry-After: 18
```

---

## Common Headers

| Header             | Description                        |
|--------------------|------------------------------------|
| `X-Request-ID`     | Client-generated request UUID      |
| `X-Real-IP`        | Client IP behind reverse proxy     |
| `Accept-Encoding`  | `gzip` compression supported       |

---

## Versions

Current API version: **v1**  
Version is path-prefixed: `/api/v1/...`  
Deprecated versions remain available for one release cycle.
