"""Custom ASGI middleware and security validation utilities."""

from __future__ import annotations

import re
import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.app.core.exceptions import SecurityException


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Injects unique correlation IDs and performance headers on each request."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()
        request_id = request.headers.get("X-Request-ID") or request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)

        process_time_ms = (time.perf_counter() - start_time) * 1000.0
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{process_time_ms:.2f}"
        return response


SAFE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]+$")


def sanitize_safe_id(raw_id: str, field_name: str = "identifier") -> str:
    """Validate that an identifier contains no path traversal or dangerous characters."""
    if not raw_id or not isinstance(raw_id, str):
        raise SecurityException(f"Invalid {field_name}: cannot be empty.")
    
    cleaned = raw_id.strip()
    if ".." in cleaned or "/" in cleaned or "\\" in cleaned:
        raise SecurityException(f"Path traversal characters detected in {field_name}.")
    
    if not SAFE_ID_REGEX.match(cleaned):
        raise SecurityException(f"Special characters detected in {field_name}. Only alphanumeric, hyphen, underscore, and dot are allowed.")
    
    return cleaned
