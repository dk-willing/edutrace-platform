"""End-to-end walkthrough:  python -m edutrace.demo

Scores a simulated cohort, takes the top learner through review and
notification, shows what the guardian would actually receive, and shows what
the system refuses to do.
"""

from __future__ import annotations

import sys

import numpy as np

from .contract import RiskTier
from .conversation.protocol import ConversationGuide
from .conversation.safeguarding import Category, escalate
from .features import build_frame
from .messaging import Dispatcher
from .messaging import templates as tmpl
from .messaging.dispatcher import MessageRejected
from .messaging.providers import ConsoleProvider
from .serve.review import ReviewDecision, ReviewRequest, apply_review
from .serve.scorer import Scorer, _row_to_observation
from .simulate import SimConfig, simulate
from .train.model import ModelBundle

RULE = "=" * 78


def h(title: str) -> None:
    print(f"\n{RULE}\n{title}\n{RULE}")


def main(model_dir: str = "artifacts/model") -> int:
    try:
        bundle = ModelBundle.load(model_dir)
    except Exception as exc:  # noqa: BLE001
        print(f"could not load a model from {model_dir}: {exc}")
        print("run:  python -m edutrace.train.run --out artifacts/model")
        return 1

    scorer = Scorer(bundle)

    h("1. A cohort arrives as a CSV")
    res = simulate(SimConfig(n_schools=8, entrants_per_school=40, n_cohorts=3))
    panel = res.panel
    cohort = panel[panel.academic_year == panel.academic_year.max()]
    print(f"   {len(cohort):,} weekly observations, "
          f"{cohort.student_key.nunique():,} learners")
    print(f"   realised 8-week exit rate: {cohort.label.mean():.3%}")

    h("2. Scored, and ranked against a stated capacity")
    capacity = 20
    probs, tiers, _ = scorer.score_frame(cohort, explain_top_k=None)
    order = np.argsort(-probs)
    hit = int(cohort.label.to_numpy()[order[:capacity]].sum())
    print(f"   capacity stated by the school: {capacity} conversations")
    print(f"   of the top {capacity}, {hit} actually stopped attending "
          f"({hit / capacity:.0%} precision)")
    print(f"   picking {capacity} at random would have found "
          f"{capacity * cohort.label.mean():.1f}")
    print(f"   tier spread: "
          + ", ".join(f"{t}={int((tiers == t).sum())}" for t in
                      ("LOW", "WATCH", "ELEVATED", "HIGH")))

    h("3. The card a class teacher sees")
    top = _row_to_observation(cohort.iloc[int(order[0])])
    a = scorer.score(top)
    print(f"   risk {a.risk:.1%}   tier {a.tier.value}   "
          f"computed in {a.latency_ms:.1f} ms")
    print(f"   review required: {a.requires_human_review}")
    print("\n   what the model is weighing:")
    for d in a.drivers:
        print(f"     + {d.label:<44} {d.share:>5.0%}"
              + ("  [actionable]" if d.actionable else ""))
    for d in a.protective:
        print(f"     - {d.label:<44} {d.share:>5.0%}")
    print("\n   what would change it:")
    for s in a.recourse:
        print(f"     {'YES' if s.feasible else ' no'}  {s.note}")
    print("\n   narrative:")
    for line in _wrap(a.narrative, 72):
        print(f"     {line}")

    h("4. Nothing goes home until a human has looked")
    dispatcher = Dispatcher(ConsoleProvider(echo=False))
    text = tmpl.GUARDIAN_ATTENDANCE.body.format(
        school="Adjeikojo M/A JHS", first_name="Kofi", missed=8, total=10,
        phone="0302123456",
    )
    p = dispatcher.plan(
        tier=a.tier, student_key=a.student_key, school_id=a.school_id, term="T3",
        guardian_msisdn="0244000111", text=text, review_completed=False,
    )
    print(f"   attempt without review -> {p.channel.value}")
    print(f"   reason: {p.suppressed_reason}")

    outcome = apply_review(
        ReviewRequest(
            observation_id=a.observation_id, reviewer_id="head.owusu",
            reviewer_role="head_teacher", decision=ReviewDecision.CONFIRM,
        ),
        a.tier, a.student_key,
    )
    print(f"\n   head teacher records: {outcome.decision.value} "
          f"(tier {outcome.model_tier.value} -> {outcome.final_tier.value})")

    p = dispatcher.plan(
        tier=outcome.final_tier, student_key=a.student_key,
        school_id=a.school_id, term="T3", guardian_msisdn="0244000111",
        text=text, review_completed=outcome.notification_unlocked,
        assign_call_to="teacher.mensah",
    )
    print(f"   attempt after review  -> {p.channel.value}")
    print(f"\n   guardian receives ({p.segmentation.encoding}, "
          f"{p.segmentation.segments} segment):")
    for line in _wrap(p.text, 68):
        print(f"     | {line}")
    if p.call_task:
        print(f"\n   AND a call task for {p.call_task.assigned_to} -- because the "
              f"Botswana RCT\n   found SMS alone produced a precise zero "
              f"(d=0.024, p=0.60) while SMS plus\n   a weekly call produced "
              f"d=0.121, p=0.008. The call is the intervention.")

    h("5. What the system refuses to send")
    for bad in ("Kofi is at risk of dropping out.",
                "Kofi has a 73% chance of leaving school."):
        try:
            Dispatcher.validate_text(bad)
            print(f"   ACCEPTED (bug!): {bad}")
        except MessageRejected:
            print(f"   rejected: {bad!r}")

    h("6. After the flag: a conversation, not a psychometric test")
    g = ConversationGuide()
    print("   " + _one(g.confidentiality_script))
    print()
    for pr in g.prompts()[:4]:
        print(f"   [{pr.domain.value}] {pr.ask}")
        print(f"       -> {pr.actions[0]}")
    print("\n   The needs profile that comes out of this does NOT change the")
    print("   risk score. The actuarial estimate says who to look at; the")
    print("   conversation says what to do.")

    h("7. If a learner discloses something")
    rec = escalate("S-DEMO", "SCH001", Category.PREGNANCY_OR_PARENTING, "t.mensah")
    print(f"   category: {rec.category.value}")
    print(f"   conversation stopped: {rec.conversation_stopped}")
    print(f"   referrals required: "
          f"{', '.join(r.value for r in rec.missing_referrals())}")
    for line in _wrap(rec.guidance(), 70):
        print(f"   {line}")
    print("\n   Stored: category, who raised it, when, to whom.")
    print("   NOT stored: anything the learner said. EscalationRecord has no")
    print("   free-text field at all, and the audit log rejects one.")

    h("8. What this model must not be used for")
    for item in bundle.card.out_of_scope:
        for i, line in enumerate(_wrap(item, 70)):
            print(f"   {'-' if i == 0 else ' '} {line}")
    print(f"\n   provenance: {_one(bundle.card.data_provenance)}")
    return 0


def _wrap(text: str, width: int) -> list[str]:
    import textwrap

    return textwrap.wrap(text, width=width)


def _one(text: str) -> str:
    return " ".join(text.split())


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:] or [])))
