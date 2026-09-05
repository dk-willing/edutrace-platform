"""Outbound contact: channel escalation, provider abstraction, guard rails.

**The finding that should reshape the product.**  An SMS-only intervention does
not work.  The Botswana RCT (Angrist, Bergman & Matsheng, *Nature Human
Behaviour* 2022) is the cleanest test: SMS alone produced d = 0.024 SD,
p = 0.602 -- a precise zero.  SMS *plus a weekly phone call* produced d = 0.121,
p = 0.008, and a 31% reduction in innumeracy.  Cost: ~$5/child for SMS, ~$19
adding calls.  In northern Ghana, IPA/World Bank's parental-nudge trial found
simple-English SMS null on average and **negative** for the 65% of caregivers
with no formal schooling -- the paper is titled "A 'Smart Buy' for All?
Unequal and Unintended Consequences of a Messaging Program".  In Côte d'Ivoire,
French text versus local-language audio showed no differential effect, and a
parent-only arm *increased* reported child labour.

The design consequence is structural, not cosmetic.  SMS is the cheap, wide,
low-signal channel.  The actual intervention for a high-risk learner is a human
voice, and the system's job is to *schedule and track that call*, not to
declare victory when a text is delivered.  So ``dispatch`` escalates by tier:

    WATCH      nothing goes out. The learner appears on the class review list.
    ELEVATED   one SMS to the guardian, factual and non-alarming.
    HIGH       SMS *plus* a call task assigned to a named member of staff,
               with the call outcome required back before the case closes.

Guard rails enforced here rather than trusted to the caller:

* Nothing sends without a completed human review (Act 843 s.41).
* Nothing sends to a guardian who has opted out.
* The message never contains a risk score, a percentage, a tier name, a
  ranking, or the word "dropout". Guardians receive an attendance fact and an
  invitation, because that is what is actionable and what is not stigmatising.
* Rate limits per learner per term, so a struggling child's family is not
  texted eleven times.
* Every send is costed in segments before it goes.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from ..contract import RiskTier
from .encoding import Segmentation, prepare
from .providers.base import DeliveryResult, SmsProvider

log = logging.getLogger(__name__)


class Channel(str, Enum):
    NONE = "NONE"
    SMS = "SMS"
    SMS_PLUS_CALL = "SMS_PLUS_CALL"


#: Phrases that must never reach a guardian's handset.
BANNED_PATTERNS = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bdrop[\s-]?out\b",
        r"\bat[\s-]risk\b",
        r"\brisk score\b",
        r"\bhigh risk\b",
        r"\bprobability\b",
        # No \b after % -- '%' is not a word character, so \b would never match
        # and "73% risk" sailed straight through the filter.
        r"\d{1,3}\s?%",
        r"\bchance of\b",
        r"\blikely to (leave|stop|quit)\b",
        r"\brank(ed|ing)?\b",
        r"\bpredict(ed|ion)?\b",
        r"\bflagged\b",
    )
)


class MessageRejected(ValueError):
    pass


@dataclass(slots=True)
class CallTask:
    """A human call, which is the actual intervention."""

    student_key: str
    school_id: str
    assigned_to: str
    created_at: datetime
    reason: str
    completed: bool = False
    outcome: str | None = None


@dataclass(slots=True)
class DispatchPlan:
    channel: Channel
    text: str | None
    segmentation: Segmentation | None
    call_task: CallTask | None
    suppressed_reason: str | None = None


@dataclass(slots=True)
class DispatcherSettings:
    sender_id: str = "EDUTRACE"
    max_messages_per_learner_per_term: int = 3
    #: UEC Code of Conduct restricts *promotional* traffic to 08:00-19:00 and
    #: bans Sundays. Attendance alerts to an enrolled guardian are
    #: transactional, not promotional -- but get that classification in writing
    #: from the aggregator, because a carrier that reclassifies the traffic
    #: breaks the product.
    quiet_hours: tuple[int, int] = (20, 6)
    force_ascii: bool = True


class Dispatcher:
    def __init__(
        self,
        provider: SmsProvider,
        settings: DispatcherSettings | None = None,
        audit=None,
    ):
        self.provider = provider
        self.settings = settings or DispatcherSettings()
        self.audit = audit
        self._sent_count: dict[tuple[str, str], int] = {}
        self._opted_out: set[str] = set()
        self.call_tasks: list[CallTask] = []

    # -- consent ---------------------------------------------------------

    def opt_out(self, msisdn: str) -> None:
        self._opted_out.add(msisdn)

    def has_opted_out(self, msisdn: str) -> bool:
        return msisdn in self._opted_out

    # -- validation ------------------------------------------------------

    @staticmethod
    def validate_text(text: str) -> None:
        for pat in BANNED_PATTERNS:
            if pat.search(text):
                raise MessageRejected(
                    f"message contains disallowed phrasing matching "
                    f"{pat.pattern!r}. Guardians receive attendance facts and "
                    f"an invitation, never a risk score, a tier, or the word "
                    f"'dropout' -- naming a child as a predicted dropout to "
                    f"their family is a labelling harm with no upside."
                )

    # -- planning --------------------------------------------------------

    def plan(
        self,
        *,
        tier: RiskTier,
        student_key: str,
        school_id: str,
        term: str,
        guardian_msisdn: str | None,
        text: str,
        review_completed: bool,
        assign_call_to: str | None = None,
    ) -> DispatchPlan:
        if not review_completed:
            return DispatchPlan(
                Channel.NONE, None, None, None,
                "no completed human review -- Act 843 s.41 requires a named "
                "member of staff to review before any significant decision is "
                "acted on",
            )
        if tier in (RiskTier.LOW, RiskTier.WATCH):
            return DispatchPlan(
                Channel.NONE, None, None, None,
                "tier below ELEVATED: appears on the class review list, no "
                "contact home",
            )
        if not guardian_msisdn:
            return DispatchPlan(
                Channel.NONE, None, None, None, "no guardian number on file"
            )
        if self.has_opted_out(guardian_msisdn):
            return DispatchPlan(
                Channel.NONE, None, None, None, "guardian has opted out"
            )

        key = (student_key, term)
        if self._sent_count.get(key, 0) >= self.settings.max_messages_per_learner_per_term:
            return DispatchPlan(
                Channel.NONE, None, None, None,
                f"per-term message cap reached "
                f"({self.settings.max_messages_per_learner_per_term})",
            )

        self.validate_text(text)
        wire, seg = prepare(text, force_ascii=self.settings.force_ascii)

        call = None
        channel = Channel.SMS
        if tier is RiskTier.HIGH:
            channel = Channel.SMS_PLUS_CALL
            call = CallTask(
                student_key=student_key,
                school_id=school_id,
                assigned_to=assign_call_to or "unassigned",
                created_at=datetime.now(timezone.utc),
                reason="HIGH tier: the RCT evidence says the text alone does "
                       "nothing; the call is the intervention",
            )
        return DispatchPlan(channel, wire, seg, call)

    # -- execution -------------------------------------------------------

    def dispatch(self, plan: DispatchPlan, guardian_msisdn: str,
                 student_key: str, term: str) -> DeliveryResult | None:
        if plan.channel is Channel.NONE or plan.text is None:
            if self.audit:
                self.audit.append(
                    "notification.suppressed",
                    student_key=student_key,
                    reason=plan.suppressed_reason,
                )
            return None

        result = self.provider.send(
            to=guardian_msisdn, text=plan.text, sender_id=self.settings.sender_id
        )
        self._sent_count[(student_key, term)] = (
            self._sent_count.get((student_key, term), 0) + 1
        )
        if plan.call_task:
            self.call_tasks.append(plan.call_task)

        if self.audit:
            self.audit.append(
                "notification.sent",
                student_key=student_key,
                channel=plan.channel.value,
                segments=plan.segmentation.segments if plan.segmentation else None,
                encoding=plan.segmentation.encoding if plan.segmentation else None,
                provider=self.provider.name,
                provider_message_id=result.message_id,
                accepted=result.accepted,
                call_task_created=plan.call_task is not None,
            )
        return result


__all__ = [
    "Channel",
    "CallTask",
    "DispatchPlan",
    "Dispatcher",
    "DispatcherSettings",
    "MessageRejected",
    "BANNED_PATTERNS",
]
