"""HTTP API.

    uvicorn edutrace.serve.app:app --host 0.0.0.0 --port 8000

Shape of the thing: scoring is fast and stateless, everything that touches a
child is gated and logged.

    GET  /health                      liveness + model version
    GET  /model-card                  provenance, metrics, limitations, scope
    POST /v1/score                    one learner, with explanation
    POST /v1/score/batch              CSV upload, capacity-ranked worklist
    GET  /v1/queue/{school_id}        this week's review list, capacity-bounded
    POST /v1/review                   record a staff decision (unlocks contact)
    POST /v1/notify                   send to a guardian -- refuses without review
    GET  /v1/conversation/guide       the support-conversation protocol
    POST /v1/safeguarding/escalate    metadata-only escalation record

State lives in a process-local store.  That is honest for a demonstration and
wrong for production: swap ``Store`` for Postgres with row-level security per
school before this touches a real learner.  The interface is deliberately
narrow so that swap is mechanical.

Deployment note: nearest region to Accra is AWS af-south-1 (Cape Town), which
measures ~65 ms RTT against ~96 ms to London and ~112 ms to Dublin -- Equiano
and WACS run down the west coast.  There is no data-localisation requirement
for education data in Ghana (the Bank of Ghana rule is financial-sector only),
but af-south-1 primary with a European warm standby is both faster and more
defensible than the reverse.
"""

from __future__ import annotations

import io
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from ..contract import HORIZON_WEEKS, RiskTier, contract_fingerprint
from ..conversation.protocol import ConversationGuide, NeedsProfile
from ..conversation.safeguarding import Category, escalate
from ..messaging import Dispatcher, get_provider
from ..messaging import templates as tmpl
from ..records import BatchSummary, RiskAssessment, StudentObservation
from ..train.model import ModelBundle
from .audit import AuditLog
from .review import ReviewError, ReviewOutcome, ReviewRequest, apply_review
from .scorer import Scorer

log = logging.getLogger("edutrace.serve")

MODEL_DIR = os.environ.get(
    "EDUTRACE_MODEL_DIR",
    str(Path(__file__).resolve().parents[2] / "artifacts" / "model"),
)
AUDIT_PATH = os.environ.get("EDUTRACE_AUDIT_PATH", "artifacts/audit.jsonl")
API_KEY = os.environ.get("EDUTRACE_API_KEY")
SMS_PROVIDER = os.environ.get("EDUTRACE_SMS_PROVIDER", "console")


# --------------------------------------------------------------------------


@dataclass
class Store:
    """Process-local state.  Replace with Postgres before production."""

    assessments: dict[str, RiskAssessment] = field(default_factory=dict)
    reviews: dict[str, ReviewOutcome] = field(default_factory=dict)
    guardians: dict[str, str] = field(default_factory=dict)
    school_index: dict[str, list[str]] = field(default_factory=dict)

    def put(self, a: RiskAssessment) -> None:
        self.assessments[a.observation_id] = a
        self.school_index.setdefault(a.school_id, []).append(a.observation_id)


@dataclass
class Runtime:
    bundle: ModelBundle | None = None
    scorer: Scorer | None = None
    audit: AuditLog | None = None
    dispatcher: Dispatcher | None = None
    store: Store = field(default_factory=Store)


RT = Runtime()


@asynccontextmanager
async def lifespan(app: FastAPI):
    RT.audit = AuditLog(AUDIT_PATH)
    try:
        RT.bundle = ModelBundle.load(MODEL_DIR)
        RT.scorer = Scorer(RT.bundle)
        log.info("loaded model %s from %s", RT.bundle.card.version, MODEL_DIR)
    except Exception as exc:  # noqa: BLE001
        # Start anyway so /health can report the failure, but refuse to score.
        # A scoring service that silently serves a stale or absent model is
        # worse than one that is loudly down.
        log.error("model load failed: %s", exc)
    RT.dispatcher = Dispatcher(get_provider(SMS_PROVIDER), audit=RT.audit)
    problems = tmpl.check_all()
    if problems:
        log.warning("template segmentation problems: %s", problems)
    yield


app = FastAPI(
    title="EduTrace",
    version="0.1.0",
    lifespan=lifespan,
    description=(
        "Advisory early-warning triage for junior high school attendance. "
        "Every tier above WATCH requires a named human review before any "
        "contact is made about a learner."
    ),
)


async def require_key(x_api_key: str | None = Header(default=None)) -> None:
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(
            status_code=401, detail="invalid or missing X-API-Key")


def _scorer() -> Scorer:
    if RT.scorer is None:
        raise HTTPException(
            status_code=503,
            detail=(
                f"no model loaded from {MODEL_DIR}. Train one with "
                f"`python -m edutrace.train.run --out {MODEL_DIR}`. Refusing to "
                f"score rather than serve an absent model."
            ),
        )
    return RT.scorer


# --------------------------------------------------------------------------
# read-only
# --------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok" if RT.scorer else "degraded",
        "model_loaded": RT.scorer is not None,
        "model_version": RT.bundle.card.version if RT.bundle else None,
        "contract_fingerprint": contract_fingerprint(),
        "horizon_weeks": HORIZON_WEEKS,
        "sms_provider": RT.dispatcher.provider.name if RT.dispatcher else None,
    }


@app.get("/model-card")
async def model_card() -> dict[str, Any]:
    if RT.bundle is None:
        raise HTTPException(status_code=503, detail="no model loaded")
    from dataclasses import asdict

    return asdict(RT.bundle.card)


@app.get("/v1/conversation/guide")
async def conversation_guide(_: None = Depends(require_key)) -> dict[str, Any]:
    g = ConversationGuide()
    return {
        "instrument_type": "structured supportive conversation (non-clinical)",
        "not_a_psychometric_assessment": True,
        "why": (
            "A teacher-administered psychometric assessment of a child is "
            "outside a teacher's scope of practice, and the validated "
            "instruments are licensed against embedding in a commercial "
            "product. This protocol produces a needs profile mapped to "
            "actions, not a score."
        ),
        "confidentiality_script": g.confidentiality_script,
        "opening_script": g.opening_script,
        "stance": list(g.stance),
        "prompts": [
            {
                "id": p.id,
                "domain": p.domain.value,
                "ask": p.ask,
                "listen_for": list(p.listen_for),
                "actions": list(p.actions),
                "safeguarding_trigger": p.safeguarding_trigger,
            }
            for p in g.prompts()
        ],
        "closing_script": g.closing_script,
    }


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------


@app.post("/v1/score", response_model=RiskAssessment)
async def score(
    obs: StudentObservation, _: None = Depends(require_key)
) -> RiskAssessment:
    a = _scorer().score(obs)
    RT.store.put(a)
    if RT.audit:
        RT.audit.append(
            "score.single",
            observation_id=a.observation_id,
            student_key=a.student_key,
            school_id=a.school_id,
            risk=round(a.risk, 6),
            tier=a.tier.value,
            model_version=a.model_version,
            latency_ms=round(a.latency_ms or 0.0, 3),
        )
    return a


class BatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: BatchSummary
    worklist: list[RiskAssessment]
    guidance: str


@app.post("/v1/score/batch", response_model=BatchResponse)
async def score_batch(
    file: UploadFile = File(...),
    capacity: int = 40,
    _: None = Depends(require_key),
) -> BatchResponse:
    """Score a CSV export and return a capacity-bounded worklist.

    ``capacity`` is the number of learners the school can actually follow up
    this week. It is a required input rather than a default, because the whole
    metric story -- precision@k, recall@k -- is meaningless without it, and a
    list longer than the school can action is the failure mode that killed
    Peru's national system.
    """
    t0 = time.perf_counter()
    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail=f"could not parse CSV: {exc}")
    if df.empty:
        raise HTTPException(status_code=400, detail="CSV contained no rows")

    sc = _scorer()
    try:
        probs, tiers, assessments = sc.score_frame(df, explain_top_k=capacity)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"scoring failed: {exc}")

    for a in assessments:
        RT.store.put(a)

    counts: dict[str, int] = {}
    for t in tiers:
        counts[str(t)] = counts.get(str(t), 0) + 1

    summary = BatchSummary(
        rows_in=len(df),
        rows_scored=len(probs),
        rows_rejected=len(df) - len(probs),
        flagged_count=int(sum(1 for t in tiers if t != RiskTier.LOW.value)),
        capacity_used=len(assessments),
        tier_counts=counts,
        elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        model_version=RT.bundle.card.version if RT.bundle else "unknown",
    )
    if RT.audit:
        RT.audit.append(
            "score.batch",
            rows=summary.rows_scored,
            flagged=summary.flagged_count,
            capacity=capacity,
            elapsed_ms=round(summary.elapsed_ms, 2),
        )
    return BatchResponse(
        summary=summary,
        worklist=assessments,
        guidance=(
            f"{summary.flagged_count} learners scored above LOW, and the list "
            f"is capped at your stated capacity of {capacity}. Ranking below "
            f"that line is not meaningful -- do not work down the list. Each "
            f"entry needs a named reviewer before anything is sent home."
        ),
    )


@app.get("/v1/queue/{school_id}")
async def queue(
    school_id: str, capacity: int = 40, _: None = Depends(require_key)
) -> dict[str, Any]:
    ids = RT.store.school_index.get(school_id, [])
    items = [RT.store.assessments[i] for i in ids if i in RT.store.assessments]
    items.sort(key=lambda a: -a.risk)
    pending = [a for a in items if a.observation_id not in RT.store.reviews]
    return {
        "school_id": school_id,
        "capacity": capacity,
        "total_scored": len(items),
        "awaiting_review": len(pending),
        "worklist": pending[:capacity],
    }


# --------------------------------------------------------------------------
# review gate
# --------------------------------------------------------------------------


@app.post("/v1/review", response_model=ReviewOutcome)
async def review(
    req: ReviewRequest, _: None = Depends(require_key)
) -> ReviewOutcome:
    a = RT.store.assessments.get(req.observation_id)
    if a is None:
        raise HTTPException(status_code=404, detail="unknown observation_id")
    try:
        outcome = apply_review(req, a.tier, a.student_key)
    except ReviewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    RT.store.reviews[req.observation_id] = outcome
    if RT.audit:
        RT.audit.append(
            "review.recorded",
            observation_id=req.observation_id,
            student_key=a.student_key,
            model_tier=outcome.model_tier.value,
            final_tier=outcome.final_tier.value,
            overridden=outcome.overridden,
            decision=outcome.decision.value,
            reason=outcome.reason.value if outcome.reason else None,
            reviewer_id=outcome.reviewer_id,
            reviewer_role=outcome.reviewer_role,
        )
    return outcome


# --------------------------------------------------------------------------
# notification
# --------------------------------------------------------------------------


class NotifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: str
    guardian_msisdn: str = Field(min_length=7, max_length=20)
    first_name: str = Field(min_length=1, max_length=60)
    school_name: str = Field(min_length=1, max_length=120)
    school_phone: str = Field(min_length=7, max_length=20)
    term: str = "T1"
    missed_days: int = Field(default=0, ge=0, le=90)
    of_last_days: int = Field(default=10, ge=1, le=90)
    assign_call_to: str | None = None


@app.post("/v1/notify")
async def notify(req: NotifyRequest, _: None = Depends(require_key)) -> dict[str, Any]:
    a = RT.store.assessments.get(req.observation_id)
    if a is None:
        raise HTTPException(status_code=404, detail="unknown observation_id")
    outcome = RT.store.reviews.get(req.observation_id)

    labels = [d.label for d in a.drivers]
    template = tmpl.select(a.tier, labels)
    text = template.body.format(
        school=req.school_name,
        first_name=req.first_name,
        missed=req.missed_days,
        total=req.of_last_days,
        phone=req.school_phone,
        count=1,
    )

    plan = RT.dispatcher.plan(
        tier=outcome.final_tier if outcome else a.tier,
        student_key=a.student_key,
        school_id=a.school_id,
        term=req.term,
        guardian_msisdn=req.guardian_msisdn,
        text=text,
        review_completed=bool(outcome and outcome.notification_unlocked),
        assign_call_to=req.assign_call_to,
    )
    result = RT.dispatcher.dispatch(
        plan, req.guardian_msisdn, a.student_key, req.term
    )
    return {
        "channel": plan.channel.value,
        "suppressed_reason": plan.suppressed_reason,
        "template": template.key,
        "text": plan.text,
        "segments": plan.segmentation.segments if plan.segmentation else None,
        "encoding": plan.segmentation.encoding if plan.segmentation else None,
        "call_task_created": plan.call_task is not None,
        "accepted": result.accepted if result else False,
        "message_id": result.message_id if result else None,
    }


# --------------------------------------------------------------------------
# safeguarding
# --------------------------------------------------------------------------


class EscalateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_key: str
    school_id: str
    category: Category
    raised_by: str
    # No detail field, deliberately. See conversation/safeguarding.py.


@app.post("/v1/safeguarding/escalate")
async def safeguarding_escalate(
    req: EscalateRequest, _: None = Depends(require_key)
) -> dict[str, Any]:
    rec = escalate(
        req.student_key, req.school_id, req.category, req.raised_by, audit=RT.audit
    )
    return {
        "recorded": True,
        "category": rec.category.value,
        "guidance": rec.guidance(),
        "required_referrals": [r.value for r in rec.missing_referrals()],
        "conversation_stopped": rec.conversation_stopped,
        "note": (
            "This record stores that an escalation was raised, of what "
            "category, by whom and when. It does not store what was said, and "
            "nothing from a disclosure enters the feature store or any "
            "training data."
        ),
    }


class ProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: NeedsProfile


@app.post("/v1/conversation/profile")
async def save_profile(
    req: ProfileRequest, _: None = Depends(require_key)
) -> dict[str, Any]:
    p = req.profile
    if RT.audit:
        # Domains and action counts only -- never the notes.
        RT.audit.append(
            "conversation.profile_saved",
            student_key=p.student_key,
            school_id=p.school_id,
            conducted_by=p.conducted_by,
            domains=[d.value for d in p.domains_present],
            action_count=len(p.agreed_actions),
            escalation_raised=p.escalation_raised,
        )
    return {
        "saved": True,
        "domains_present": [d.value for d in p.domains_present],
        "suggested_actions": p.suggested_actions(),
        "affects_risk_score": False,
        "note": (
            "The needs profile does not change the model's estimate. The "
            "actuarial score says who to look at; the conversation says what "
            "to do. If staff disagree with the tier, use the bounded, "
            "reason-coded override at /v1/review."
        ),
    }


__all__ = ["app", "RT", "Store", "Runtime"]
