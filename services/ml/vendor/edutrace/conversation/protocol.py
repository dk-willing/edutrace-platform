"""The support conversation -- NOT a psychometric evaluation.

This module deliberately does not implement what was originally asked for.
Here is why, because the reasoning matters more than the code.

**A teacher-administered psychometric assessment of a child is not a thing this
product can lawfully or safely ship.**

* *Licensing.*  Nearly every validated instrument is closed to it.  The Student
  Engagement Instrument is free "for research or practice purposes" but
  explicitly "not for purposes resulting in profit".  The SDQ is copyright and
  "users are not permitted to create or distribute electronic versions for any
  purpose without prior authorization from youthinmind" -- a digital product is
  an electronic version.  RCADS forbids commercial distribution of the
  instrument or derivatives by a third party.  PSSM requires the author's
  permission.  BASC-3 BESS and BIMAS-2 are per-administration licensed and
  US-normed.  Embedding any of these without written permission is not a risk,
  it is an infringement.
* *Scope of practice.*  Ghana has a Psychology Council (Act 857).  A teacher
  administering something the software calls a "psychometric evaluation" and
  scoring a child on it is practising psychology.  Calling it a screener does
  not change that if the output looks like a clinical score.
* *Norms.*  A scoping review of SDQ use across Africa found the instrument
  widely used but its psychometric properties in African settings largely
  unestablished.  US or UK cut scores applied to Ghanaian JHS learners produce
  confident numbers that mean nothing.
* *The bright line.*  School-psychology guidance is uniform: **no screening
  without services.**  Absent a real pathway to support, flagging a child is
  not a benefit, it is a labelling harm.

**What replaces it, and why that is better anyway.**

A structured supportive conversation whose output is a *needs profile* -- a set
of concrete barriers, each mapped to a concrete action -- rather than a score.
The spine is WHO Psychological First Aid's Look / Listen / Link, explicitly
designed so that "it is not necessary to have a 'psychosocial' background", and
deliberately *not* probing for trauma detail.  The questioning stance is
motivational interviewing, which a 2024 meta-analysis of 38 school-based
studies (207 effect sizes) found effective, which is teachable to
non-clinicians, and which is non-diagnostic by construction.  The structure of
the relationship is Check & Connect's mentor protocol -- the model the What
Works Clearinghouse rates as having positive effects on *staying in school* --
imitated rather than licensed.

**The output never changes the risk score.**  Two channels stay separate: the
actuarial estimate says who to look at; the conversation says what to do.  The
risk-assessment literature is clear that unbounded clinical override degrades
accuracy and encodes bias; and training a model on teacher-entered perception
creates a loop where the model's ground truth becomes the teacher's opinion.
If staff disagree with the tier, that goes through the bounded, reason-coded
override in ``edutrace.serve.review`` -- one step, logged, auditable.

The one *scored* element retained is a brief teacher-rated behavioural screener
modelled on the SRSS-IE, which is free-access, teacher-completed, takes about
fifteen seconds, and has documented predictive validity for course failure and
disciplinary outcomes in samples of ~11,700 middle-school students.  Even that
ships **unscored by default** until locally re-normed: the published cut points
are US-derived.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Domain(str, Enum):
    """Barrier domains.  Each maps to an action, never to a diagnosis."""

    COST = "COST"
    JOURNEY = "JOURNEY"
    WORK_AND_CARE = "WORK_AND_CARE"
    HEALTH = "HEALTH"
    LEARNING = "LEARNING"
    BELONGING = "BELONGING"
    SAFETY = "SAFETY"
    ASPIRATION = "ASPIRATION"


@dataclass(frozen=True, slots=True)
class Prompt:
    """One open question, plus what to listen for and what it unlocks.

    Open questions, in the learner's words.  Nothing here asks a child to rate
    themselves on a scale, because a scale invites a score and a score invites
    a diagnosis.
    """

    id: str
    domain: Domain
    ask: str
    listen_for: tuple[str, ...]
    #: Practical supports a Ghanaian JHS could actually mobilise.
    actions: tuple[str, ...]
    safeguarding_trigger: bool = False


PROMPTS: tuple[Prompt, ...] = (
    Prompt(
        "open", Domain.ASPIRATION,
        "How have the last few weeks of school been going for you?",
        ("anything the learner raises first -- that is usually the real one",),
        ("Note the learner's own framing before offering any of your own.",),
    ),
    Prompt(
        "cost", Domain.COST,
        "Is there anything about school costs -- levies, books, uniform -- that "
        "has been difficult at home lately?",
        ("levies outstanding", "no textbooks", "uniform worn out or missing",
         "asked to stay home until fees are paid"),
        ("Refer to the head teacher for levy waiver or a payment schedule.",
         "Check capitation-grant coverage; the learner may be exempt already.",
         "Textbook loan from the school stock.",
         "PTA hardship fund referral."),
    ),
    Prompt(
        "journey", Domain.JOURNEY,
        "Tell me about getting to school -- how long does it take, and what "
        "makes it harder some days?",
        ("long walk", "flooding in the rainy season", "transport cost",
         "unsafe route", "leaves home before eating"),
        ("Buddy/walking group with learners on the same route.",
         "Adjusted first-period expectations during the rainy term.",
         "Raise persistent route safety with the head teacher and community."),
    ),
    Prompt(
        "work", Domain.WORK_AND_CARE,
        "What do you usually need to do at home or outside school on a normal "
        "week?",
        ("farm or market work", "caring for a sibling or relative",
         "trading in the evenings", "seasonal work absences"),
        ("Timetable flexibility during peak farm or market periods.",
         "Homework club so schoolwork does not depend on evening time at home.",
         "Conversation with the guardian about the schooling trade-off."),
    ),
    Prompt(
        "health", Domain.HEALTH,
        "How have you been feeling in yourself -- eating, sleeping, energy at "
        "school?",
        ("hunger", "recurrent illness", "untreated condition",
         "menstrual hygiene needs", "very tired in class"),
        ("School feeding programme referral where available.",
         "School nurse or nearest CHPS compound referral.",
         "Menstrual hygiene provision and a private changing option.",
         "If any disclosure concerns wellbeing or safety, STOP and follow the "
         "safeguarding escalation."),
        safeguarding_trigger=True,
    ),
    Prompt(
        "learning", Domain.LEARNING,
        "Which subjects are going alright, and which ones feel hardest right "
        "now?",
        ("specific subject collapse", "cannot follow the language of "
         "instruction", "missed foundational content", "no place to study"),
        ("Targeted small-group support in the named subject.",
         "Peer tutoring pairing.",
         "Catch-up plan for content missed during absence."),
    ),
    Prompt(
        "belonging", Domain.BELONGING,
        "Who at school do you talk to when something is bothering you?",
        ("names no one", "isolated from peers", "conflict with a teacher",
         "being bullied"),
        ("Assign a named check-in adult -- the Check & Connect pattern.",
         "Peer-group placement.",
         "If bullying is described, follow the school's own procedure."),
        safeguarding_trigger=True,
    ),
    Prompt(
        "future", Domain.ASPIRATION,
        "When you think about finishing JHS and the BECE, what comes to mind?",
        ("does not expect to finish", "no plan after JHS",
         "family expects them to stop", "not registered for the BECE"),
        ("Confirm BECE registration status today.",
         "Connect to an older learner or alumnus from the same community.",
         "Bring the guardian into a conversation about what completing enables."),
    ),
    Prompt(
        "close", Domain.ASPIRATION,
        "If the school could change one thing to make staying easier, what "
        "would it be?",
        ("the learner's own priority -- weight it above your own reading",),
        ("Record it verbatim in the needs profile and act on it first if it is "
         "within the school's power.",),
    ),
)


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_id: str
    domain: Domain
    present: bool
    #: Short operational note. Never a disclosure about abuse, self-harm,
    #: sexual activity, pregnancy or health status -- those go through the
    #: safeguarding path, which records metadata only.
    note: str = Field(default="", max_length=280)


class NeedsProfile(BaseModel):
    """The output of a conversation: barriers and actions, never a score."""

    model_config = ConfigDict(extra="forbid")

    student_key: str
    school_id: str
    conducted_by: str
    conducted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    findings: list[Finding] = Field(default_factory=list)
    agreed_actions: list[str] = Field(default_factory=list)
    review_date: str | None = None
    escalation_raised: bool = False

    #: Present so that anything reading this object cannot mistake it for a
    #: clinical instrument, including a future maintainer.
    instrument_type: str = "structured supportive conversation (non-clinical)"
    not_a_diagnosis: bool = True

    @property
    def domains_present(self) -> list[Domain]:
        return [f.domain for f in self.findings if f.present]

    def suggested_actions(self) -> list[str]:
        """Actions implied by the domains raised, deduplicated in order."""
        by_domain: dict[Domain, tuple[str, ...]] = {}
        for p in PROMPTS:
            by_domain.setdefault(p.domain, ())
            by_domain[p.domain] = by_domain[p.domain] + p.actions
        seen: set[str] = set()
        out: list[str] = []
        for d in self.domains_present:
            for a in by_domain.get(d, ()):
                if a not in seen:
                    seen.add(a)
                    out.append(a)
        return out


@dataclass(slots=True)
class ConversationGuide:
    """What the app puts in front of a teacher, in order."""

    opening_script: str = (
        "Sit somewhere private but visible. Say, in your own words: \"I asked "
        "to talk because I want to know how school is going for you, and "
        "whether there's anything we could do differently. You don't have to "
        "answer anything you don't want to.\" Do not mention the system, a "
        "list, or that the learner was identified by anything."
    )
    stance: tuple[str, ...] = field(
        default_factory=lambda: (
            "Ask, then stop talking. The silence is doing the work.",
            "Reflect back what you heard before moving on.",
            "Do not diagnose, label, or reassure prematurely.",
            "Do not probe for detail about anything distressing -- Look, "
            "Listen, Link. Your job is to connect, not to treat.",
            "The learner's own answer to the last question outranks your "
            "reading of the situation.",
        )
    )
    closing_script: str = (
        "End with something concrete and small that you will actually do, and "
        "a date you will check back. Do not promise what you cannot deliver, "
        "and do not tell the learner they are 'at risk' of anything."
    )
    confidentiality_script: str = (
        "Say this before you start, every time: \"What you tell me stays "
        "between us, unless you tell me something that makes me worried about "
        "your safety -- then I have to tell someone whose job it is to help. "
        "I would tell you first.\""
    )

    def prompts(self) -> tuple[Prompt, ...]:
        return PROMPTS


__all__ = [
    "Domain",
    "Prompt",
    "PROMPTS",
    "Finding",
    "NeedsProfile",
    "ConversationGuide",
]
