"""Show the safety net on a realistic weekly run:  python -m edutrace.triage_demo"""

from __future__ import annotations

import sys

import numpy as np

from .features import build_frame
from .simulate import SimConfig, simulate
from .train.model import ModelBundle
from .triage import Floors, coverage, triage


def main(model_dir: str = "artifacts/model", capacity: int = 20) -> int:
    try:
        bundle = ModelBundle.load(model_dir)
    except Exception as exc:  # noqa: BLE001
        print(f"could not load {model_dir}: {exc}")
        print("run:  make train")
        return 1

    res = simulate(SimConfig(n_schools=20, entrants_per_school=45, n_cohorts=4))
    panel = res.panel
    latest = panel.academic_year.max()
    wk = panel[
        (panel.academic_year == latest) & (panel.term == "T2") & (panel.week == 9)
    ].reset_index(drop=True)

    y = wk.label.to_numpy().astype(int)
    p = bundle.predict(build_frame(wk, bundle.norm_context))
    mt = np.array([bundle.tier(v).value for v in p], dtype=object)

    print("=" * 78)
    print(f"Weekly run: {len(wk):,} learners, Term 2 week 9, capacity {capacity}")
    print("=" * 78)

    floors = Floors()
    problems = floors.validate(wk)
    print("\nfloor validation: " + (
        "all rules within the 10% trip budget" if not problems
        else "\n  ".join(problems)
    ))

    r = triage(wk, p, mt, capacity=capacity, floors=floors)
    print(f"\nslot allocation: {r.floor_slots_used} to floor cases, "
          f"{r.model_slots_used} to model ranking "
          f"({r.over_capacity} learners above LOW did not fit)")

    print("\nThe worklist:")
    print(f"  {'#':>3} {'tier':<9}{'risk':>7}  reason")
    for rank, i in enumerate(r.worklist[:12], 1):
        why = r.floor_reasons[i][0] if r.floor_reasons[i] else "model ranking"
        print(f"  {rank:>3} {r.tier[i]:<9}{p[i]:>7.1%}  {why}")
    if len(r.worklist) > 12:
        print(f"      ... and {len(r.worklist) - 12} more")

    print()
    print(coverage(wk, y, p, r).render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
