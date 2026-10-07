"""HTTP adapter for standalone transcripts."""

from __future__ import annotations

from typing import Any

import requests


class BackendCommandError(RuntimeError):
    """The backend could not process a transcript."""


class BackendCommandClient:
    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def process(self, transcript: str) -> dict[str, Any]:
        try:
            response = requests.post(
                f"{self.base_url}/api/game/command",
                json={"control": transcript},
                timeout=self.timeout,
            )
        except requests.exceptions.Timeout as error:
            raise BackendCommandError(
                "Backend command timed out. Is the server running?"
            ) from error
        except requests.exceptions.RequestException as error:
            raise BackendCommandError(
                "Could not connect to the backend. Is the server running?"
            ) from error
        if not response.ok:
            try:
                detail = response.json().get("detail", "request rejected")
            except ValueError:
                detail = "request rejected"
            code = detail.get("code") if isinstance(detail, dict) else detail
            raise BackendCommandError(
                f"Backend command failed ({response.status_code}): {code}"
            )
        try:
            result = response.json()
        except ValueError as error:
            raise BackendCommandError("Backend returned an invalid command response.") from error
        if not isinstance(result, dict):
            raise BackendCommandError("Backend returned an invalid command response.")
        return result
