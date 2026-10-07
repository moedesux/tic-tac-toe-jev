"""Request-local, provider-neutral Jev exchange capture."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import os
import re
from typing import Any


@dataclass
class JevExchange:
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None


_current_exchange: ContextVar[JevExchange | None] = ContextVar("jev_exchange", default=None)


def debug_enabled() -> bool:
    return os.getenv("JEV_DEBUG", "").lower() == "true"


@contextmanager
def capture_exchange(enabled: bool):
    exchange = JevExchange() if enabled else None
    token = _current_exchange.set(exchange)
    try:
        yield exchange
    finally:
        _current_exchange.reset(token)


def current_exchange() -> JevExchange | None:
    return _current_exchange.get()


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[redacted]" if str(key).lower().replace("-", "_") in {
                "api_key", "authorization", "access_token", "password", "secret", "headers"
            } else sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        secret = os.getenv("TYPESAFE_API_KEY")
        value = value.replace(secret, "[redacted]") if secret else value
        return re.sub(
            r"\b(?:authorization\s*:\s*(?:bearer\s+)?|bearer\s+|[\w-]*(?:key|token|secret|password)[\w-]*\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)",
            "[redacted]",
            value,
            flags=re.IGNORECASE,
        )
    return value
