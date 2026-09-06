"""Production entrypoint for the EduTrace ML service.

This module does NOT reimplement scoring, explanation, review, notification,
or safeguarding logic -- all of that is the vendored ``edutrace`` package,
unmodified, imported here. What this module adds:

1. Service-to-service HMAC authentication in front of every route except the
   liveness probe (see ``service_auth.py``), so the vendored app's own
   ``X-API-Key`` check is defence-in-depth rather than the only gate.
2. Read-only model registry endpoints (``/internal/v1/models/*``) that let
   ``apps/api`` discover every model artifact this deployment has access to,
   for its own governance table -- WITHOUT granting the ability to switch
   which model is actively scoring. The vendored app loads exactly one model
   per process, from ``EDUTRACE_MODEL_DIR``, at startup; that stays true here.
   Multi-model hot-swap is out of scope for this phase and would be a
   deliberate, reviewed change to ``edutrace.serve.app``, not something to
   bolt on from outside it.
3. CORS is intentionally NOT configured -- this service has no browser
   clients, ever (Section 6: never expose the ML service to the public
   internet, let alone to a browser origin).

Run with:
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations
from .service_auth import ServiceAuthMiddleware
from edutrace.train.model import ModelBundle
from edutrace.serve.app import RT, app, require_key  # the vendored FastAPI app

import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

# Load local configuration before importing modules that initialize auth/model
# state. Production deployments should provide environment variables directly.
service_root = Path(__file__).resolve().parents[1]
load_dotenv(service_root.parents[1] / ".env")
if not os.environ.get("EDUTRACE_MODEL_DIR") or os.environ["EDUTRACE_MODEL_DIR"] == "artifacts/model":
    os.environ["EDUTRACE_MODEL_DIR"] = str(
        service_root / "vendor" / "artifacts" / "model")


log = logging.getLogger("edutrace.ml_wrapper")

app.add_middleware(ServiceAuthMiddleware)


class StaffAlertRequest(BaseModel):
    teacher_msisdn: str = Field(min_length=7, max_length=20)
    school_name: str = Field(min_length=1, max_length=120)
    urgent_count: int = Field(ge=1, le=10000)


@app.post("/internal/v1/notify/staff")
async def notify_staff(req: StaffAlertRequest, _: None = Depends(require_key)):
    if RT.dispatcher is None:
        raise HTTPException(
            status_code=503, detail="SMS provider is unavailable")
    if RT.dispatcher.provider.name != "arkesel":
        raise HTTPException(
            status_code=503,
            detail="Arkesel is not configured as the teacher SMS provider",
        )
    text = (
        f"EduTrace: {req.urgent_count} learner(s) at {req.school_name} "
        "need urgent support. Please open the review list today."
    )
    provider = RT.dispatcher.provider
    result = provider.send(
        to=provider.normalise_msisdn(req.teacher_msisdn),
        text=text,
        sender_id=RT.dispatcher.settings.sender_id,
    )
    if RT.audit:
        RT.audit.append(
            "notification.staff_urgent_support",
            school_id=req.school_name,
            urgent_count=req.urgent_count,
            provider=provider.name,
            accepted=result.accepted,
            message_id=result.message_id,
        )
    return {
        "accepted": result.accepted,
        "provider": provider.name,
        "message_id": result.message_id,
    }

# Directories this deployment knows about, for registry discovery only.
# EDUTRACE_MODEL_DIR (the one actually loaded for scoring) is always included.
_CANDIDATE_ARTIFACT_DIRS = [
    Path("vendor/artifacts/model"), Path("vendor/artifacts/oulad")]
KNOWN_ARTIFACT_DIRS = [p for p in _CANDIDATE_ARTIFACT_DIRS if p.exists()]


def _read_card(directory: Path) -> dict[str, Any] | None:
    """Read a model's provenance card without loading the booster.

    Deliberately avoids ``ModelBundle.load`` here: that call loads the full
    XGBoost booster into memory and validates the contract fingerprint against
    the *running* code, which is correct for the model actually being served
    but wasteful and occasionally wrong for a registry listing of every model
    that merely exists on disk (a retired model trained against an older
    contract should still be listable, just never loadable for scoring).
    """
    bundle_path = directory / "bundle.json"
    if not bundle_path.exists():
        return None
    try:
        payload = json.loads(bundle_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("could not read model card at %s: %s", bundle_path, exc)
        return None
    card = payload.get("card", {})
    card["_artifact_dir"] = str(directory)
    return card


@app.get("/internal/v1/models/active")
async def active_model(_: None = Depends(require_key)) -> dict[str, Any]:
    """The model currently loaded and actively scoring in this process."""
    if RT.bundle is None:
        raise HTTPException(
            status_code=503, detail="no model currently loaded")
    from dataclasses import asdict

    return {"active": True, "card": asdict(RT.bundle.card)}


@app.get("/internal/v1/models")
async def list_models(_: None = Depends(require_key)) -> dict[str, Any]:
    """Every model artifact this deployment can see, for registry sync.

    apps/api polls this on a schedule and upserts a ModelRegistration row per
    version returned, defaulting new versions to DEVELOPMENT status. This
    endpoint does not and must not imply approval -- that determination is
    made in apps/api's registry, by a human, per docs/ARCHITECTURE.md.
    """
    cards = []
    for d in KNOWN_ARTIFACT_DIRS:
        card = _read_card(d)
        if card:
            cards.append(card)
    active_version = RT.bundle.card.version if RT.bundle else None
    for c in cards:
        c["_currently_active"] = c.get("version") == active_version
    return {"models": cards}


@app.get("/internal/v1/models/{version}")
async def get_model(version: str, _: None = Depends(require_key)) -> dict[str, Any]:
    for d in KNOWN_ARTIFACT_DIRS:
        card = _read_card(d)
        if card and card.get("version") == version:
            return {"card": card, "currently_active": (
                RT.bundle is not None and RT.bundle.card.version == version
            )}
    raise HTTPException(
        status_code=404, detail=f"no known model artifact with version {version}")


__all__ = ["app"]
