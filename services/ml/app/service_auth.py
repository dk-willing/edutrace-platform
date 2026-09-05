"""Service-to-service authentication for the internal ML API.

The vendored ``edutrace.serve.app`` ships a single shared ``X-API-Key`` check
(``require_key``), which is fine for a demo and wrong for a service that must
never be reachable except from ``apps/api`` (Section 6). This module adds an
HMAC-signed, replay-resistant layer in front of it. The vendored app's own
``require_key`` stays in place underneath as defence in depth -- removing it
would be "loosening a guard to make integration easier", which the project
brief explicitly says not to do.

Signature scheme, matching docs/ARCHITECTURE.md:

    X-Service-Id:        edutrace-api
    X-Service-Timestamp: <unix ms>
    X-Service-Signature: hex(HMAC_SHA256(secret, serviceId + "." + timestamp + "." + rawBody))

Requests older than ``MAX_CLOCK_SKEW_SECONDS`` are rejected outright, so a
captured request cannot be replayed indefinitely.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

MAX_CLOCK_SKEW_SECONDS = 60

# Paths reachable without the service signature: only the liveness probe.
# Orchestrators (k8s/ECS) hit this directly and cannot practically sign a
# request, so it must stay open -- it reveals only "process is up", nothing
# about a learner.
UNAUTHENTICATED_PATHS = {"/health"}


class MissingSharedSecretError(RuntimeError):
    pass


class ServiceAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, shared_secret: str | None = None):
        super().__init__(app)
        self.shared_secret = shared_secret or os.environ.get("ML_SERVICE_SHARED_SECRET")
        if not self.shared_secret:
            raise MissingSharedSecretError(
                "ML_SERVICE_SHARED_SECRET is not set. Refusing to start the ML "
                "service without it -- an unauthenticated internal API is "
                "exactly the exposure Section 6 forbids."
            )

    async def dispatch(self, request: Request, call_next):
        if request.url.path in UNAUTHENTICATED_PATHS:
            return await call_next(request)

        service_id = request.headers.get("x-service-id")
        timestamp = request.headers.get("x-service-timestamp")
        signature = request.headers.get("x-service-signature")

        if not (service_id and timestamp and signature):
            return _reject("missing service authentication headers")

        try:
            ts = int(timestamp)
        except ValueError:
            return _reject("malformed X-Service-Timestamp")

        now_ms = int(time.time() * 1000)
        if abs(now_ms - ts) > MAX_CLOCK_SKEW_SECONDS * 1000:
            return _reject("stale or future-dated request signature")

        body = await request.body()
        expected = _sign(self.shared_secret, service_id, timestamp, body)
        if not hmac.compare_digest(expected, signature):
            return _reject("invalid service signature")

        # Starlette buffers the body when we call request.body() above, so
        # downstream handlers can still read it via the usual request.json().
        return await call_next(request)


def _sign(secret: str, service_id: str, timestamp: str, body: bytes) -> str:
    message = service_id.encode() + b"." + timestamp.encode() + b"." + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def _reject(reason: str) -> JSONResponse:
    return JSONResponse(status_code=401, content={"detail": f"service auth failed: {reason}"})


__all__ = ["ServiceAuthMiddleware", "MissingSharedSecretError"]
