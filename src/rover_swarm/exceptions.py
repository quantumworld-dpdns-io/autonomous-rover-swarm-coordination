from __future__ import annotations


class RoverSwarmError(Exception):
    """Base exception for all rover-swarm errors."""


class ConfigurationError(RoverSwarmError):
    """Raised when configuration is invalid."""


class CrdtError(RoverSwarmError):
    """Base CRDT operation error."""


class CrdtMergeError(CrdtError):
    """Raised when CRDT merge fails."""


class CrdtConflictError(CrdtError):
    """Raised when CRDT conflict cannot be resolved automatically."""


class CrdtSerializationError(CrdtError):
    """Raised when CRDT serialize/deserialize fails."""


class CommunicationError(RoverSwarmError):
    """Base communication error."""


class MqttError(CommunicationError):
    """Raised on MQTT failures."""


class GrpcError(CommunicationError):
    """Raised on gRPC failures."""


class ConnectionTimeoutError(CommunicationError):
    """Raised when connection times out."""


class NetworkPartitionError(CommunicationError):
    """Raised when network partition is detected."""


class SwarmError(RoverSwarmError):
    """Base swarm coordination error."""


class ConsensusError(SwarmError):
    """Raised when consensus cannot be reached."""


class TaskAllocationError(SwarmError):
    """Raised on task allocation failure."""


class RoverNotFoundError(SwarmError):
    """Raised when a rover is not found in the swarm."""


class SensorError(RoverSwarmError):
    """Base sensor error."""


class SensorCalibrationError(SensorError):
    """Raised when sensor calibration fails."""


class SensorReadError(SensorError):
    """Raised when sensor read fails."""


class VectorDbError(RoverSwarmError):
    """Base vector database error."""


class VectorDbConnectionError(VectorDbError):
    """Raised when vector DB connection fails."""


class VectorDbQueryError(VectorDbError):
    """Raised on vector query failure."""


class AiError(RoverSwarmError):
    """Base AI/ML error."""


class ModelNotFoundError(AiError):
    """Raised when AI model is not found."""


class ModelInferenceError(AiError):
    """Raised on inference failure."""


class SecurityError(RoverSwarmError):
    """Base security error."""


class AuthenticationError(SecurityError):
    """Raised on authentication failure."""


class AuthorizationError(SecurityError):
    """Raised on authorization failure."""


class RateLimitError(SecurityError):
    """Raised when rate limit is exceeded."""


class ApiError(RoverSwarmError):
    """Base API error."""


class NotFoundError(ApiError):
    """Raised when resource is not found."""


class ValidationError(ApiError):
    """Raised on request validation failure."""
