"""Provider-neutral operational state for the TypeSafe command boundary."""

from dataclasses import dataclass
from enum import Enum
import os
from threading import Lock
from typing import Any


class TypeSafeHealthStatus(str, Enum):
    """Passive states exposed by the TypeSafe health endpoint."""

    UNCONFIGURED = "unconfigured"
    UNVERIFIED = "unverified"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class TypeSafeOutcome(str, Enum):
    """Cached outcome of the last real command request."""

    SUCCESS = "success"
    FAILURE = "failure"


class TypeSafeFailureKind(str, Enum):
    """Provider-neutral failure categories crossing the interpreter seam."""

    NOT_CONFIGURED = "not_configured"
    AUTHENTICATION = "authentication"
    TRANSPORT = "transport"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    OVERLOAD = "overload"
    SERVICE_UNAVAILABLE = "service_unavailable"
    BAD_REQUEST = "bad_request"
    MALFORMED_RESPONSE = "malformed_response"
    UNKNOWN = "unknown"


class TypeSafeOperationalError(Exception):
    """A sanitized provider-neutral command service failure."""

    def __init__(self, kind: TypeSafeFailureKind, request_id: str | None = None) -> None:
        super().__init__(kind.value)
        self.kind = kind
        self.request_id = request_id


class MissingTypeSafeConfigurationError(TypeSafeOperationalError):
    """Raised when natural-language commands are requested without credentials."""

    def __init__(self) -> None:
        super().__init__(TypeSafeFailureKind.NOT_CONFIGURED)


@dataclass
class TypeSafeHealth:
    """Cached health; reading this object never performs I/O."""

    status: TypeSafeHealthStatus = TypeSafeHealthStatus.UNVERIFIED
    last_outcome: TypeSafeOutcome | None = None
    model: str | None = None

    def __post_init__(self) -> None:
        self._lock = Lock()

    def configured(self) -> bool:
        return bool(os.getenv("TYPESAFE_API_KEY"))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            status = self.status if self.configured() else TypeSafeHealthStatus.UNCONFIGURED
            result: dict[str, Any] = {"status": status, "service": "TypeSafe"}
            if self.model:
                result["model"] = self.model
            if self.last_outcome:
                result["last_outcome"] = self.last_outcome
            return result

    def record(self, *, success: bool, model: str | None = None) -> None:
        with self._lock:
            self.status = (
                TypeSafeHealthStatus.HEALTHY
                if success
                else TypeSafeHealthStatus.DEGRADED
            )
            self.last_outcome = TypeSafeOutcome.SUCCESS if success else TypeSafeOutcome.FAILURE
            if model:
                self.model = model

    def record_unavailable(self, model: str | None = None) -> None:
        with self._lock:
            self.status = TypeSafeHealthStatus.UNAVAILABLE
            self.last_outcome = TypeSafeOutcome.FAILURE
            if model:
                self.model = model

    def reset(self) -> None:
        with self._lock:
            self.status, self.last_outcome, self.model = TypeSafeHealthStatus.UNVERIFIED, None, None


@dataclass(frozen=True)
class TypeSafeFailureMapping:
    """Stable public HTTP and health behavior for one failure category."""

    http_status: int
    code: str
    health_status: TypeSafeHealthStatus


FAILURE_MAPPINGS = {
    TypeSafeFailureKind.NOT_CONFIGURED: TypeSafeFailureMapping(503, "typesafe_not_configured", TypeSafeHealthStatus.UNCONFIGURED),
    TypeSafeFailureKind.AUTHENTICATION: TypeSafeFailureMapping(401, "typesafe_authentication_failed", TypeSafeHealthStatus.UNAVAILABLE),
    TypeSafeFailureKind.TRANSPORT: TypeSafeFailureMapping(502, "typesafe_transport_failed", TypeSafeHealthStatus.UNAVAILABLE),
    TypeSafeFailureKind.TIMEOUT: TypeSafeFailureMapping(504, "typesafe_timeout", TypeSafeHealthStatus.DEGRADED),
    TypeSafeFailureKind.RATE_LIMIT: TypeSafeFailureMapping(429, "typesafe_rate_limited", TypeSafeHealthStatus.DEGRADED),
    TypeSafeFailureKind.OVERLOAD: TypeSafeFailureMapping(503, "typesafe_overloaded", TypeSafeHealthStatus.DEGRADED),
    TypeSafeFailureKind.SERVICE_UNAVAILABLE: TypeSafeFailureMapping(503, "typesafe_service_unavailable", TypeSafeHealthStatus.UNAVAILABLE),
    TypeSafeFailureKind.BAD_REQUEST: TypeSafeFailureMapping(400, "typesafe_bad_request", TypeSafeHealthStatus.UNAVAILABLE),
    TypeSafeFailureKind.MALFORMED_RESPONSE: TypeSafeFailureMapping(502, "typesafe_malformed_response", TypeSafeHealthStatus.UNAVAILABLE),
    TypeSafeFailureKind.UNKNOWN: TypeSafeFailureMapping(502, "typesafe_request_failed", TypeSafeHealthStatus.UNAVAILABLE),
}


def map_typesafe_error(error: TypeSafeOperationalError) -> TypeSafeFailureMapping:
    """Return the stable public behavior for a sanitized operational error."""
    return FAILURE_MAPPINGS[error.kind]


typesafe_health = TypeSafeHealth()
