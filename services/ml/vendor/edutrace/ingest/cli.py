"""Ingest CLI.

    python -m edutrace.ingest.cli check    dhs  GHPR8AFL.DTA
    python -m edutrace.ingest.cli convert  dhs  GHPR8AFL.DTA --out data/ghana_dhs.csv
    python -m edutrace.ingest.cli convert  mics gh_mics6.sav --map my_map.json --out ...
    python -m edutrace.ingest.cli convert  yl   yl_constructed.dta --out data/yl.csv
    python -m edutrace.ingest.cli convert  emis school_register.csv --daily --out ...
    python -m edutrace.ingest.cli template dhs  --out dhs_map.json

Always run ``check`` first.  It prints the enrolment-transition crosstab, which
is the one thing that catches a swapped current/previous mapping — the error
that silently inverts the label and yields a confident, backwards model.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .base import ColumnMap
from . import emis, household, oulad, young_lives


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="edutrace.ingest.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="print the transition crosstab; verify first")
    c.add_argument("source", choices=["dhs", "mics"])
    c.add_argument("path")
    c.add_argument("--map")

    v = sub.add_parser("convert", help="write a training panel")
    v.add_argument("source", choices=["dhs", "mics", "yl", "emis", "oulad"])
    v.add_argument("path")
    v.add_argument("--out", required=True)
    v.add_argument("--map")
    v.add_argument("--age-lo", type=int, default=None)
    v.add_argument("--age-hi", type=int, default=None)
    v.add_argument("--daily", action="store_true", help="emis: daily registers")
    v.add_argument("--exit-gap-weeks", type=int, default=4)
    v.add_argument("--force", action="store_true",
                   help="write even if quality checks fail (not recommended)")

    t = sub.add_parser("template", help="write a starter column map to edit")
    t.add_argument("source", choices=["dhs", "mics", "yl"])
    t.add_argument("--out", required=True)

    args = ap.parse_args(argv)

    if args.cmd == "template":
        cm = {
            "dhs": household.DHS_DEFAULT,
            "mics": household.MICS_DEFAULT,
            "yl": young_lives.YL_DEFAULT,
        }[args.source]
        p = cm.save(args.out)
        print(f"wrote {p}")
        print("Edit the 'columns' map to match your file, then pass --map.")
        return 0

    colmap = ColumnMap.load(args.map) if getattr(args, "map", None) else None

    if args.cmd == "check":
        print(household.crosstab(args.path, args.source, colmap))
        return 0

    if args.source in ("dhs", "mics"):
        panel, report = household.load(
            args.path, survey=args.source, colmap=colmap,
            age_lo=args.age_lo, age_hi=args.age_hi,
        )
    elif args.source == "yl":
        panel, report = young_lives.load(
            args.path, colmap=colmap, age_lo=args.age_lo, age_hi=args.age_hi
        )
    elif args.source == "oulad":
        panel, report = oulad.load(args.path)
    else:
        panel, report = emis.load(
            args.path,
            emis.EmisSpec(
                granularity="daily" if args.daily else "weekly",
                exit_gap_weeks=args.exit_gap_weeks,
            ),
        )

    print(report.render())
    if not report.ok() and not args.force:
        print("\nRefusing to write. Re-run with --force only if you understand "
              "why each problem above is acceptable.")
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(out, index=False)

    # Provenance sidecar. The training run picks this up automatically, so the
    # model card records what the model was actually fitted to rather than a
    # temp-file path. Provenance that lives only in someone's memory is not
    # provenance.
    sidecar = out.with_suffix(out.suffix + ".provenance.txt")
    # Build the list first and join once. Writing this as adjacent f-strings
    # followed by `"\n".join(...)` silently concatenates the literals and then
    # calls .join on the whole header, using it as the separator -- which
    # produces a provenance record with the source line repeated between every
    # warning. It looks almost right, which is why it survived a glance.
    lines = [
        f"source: {report.source}",
        f"rows: {report.rows_out:,} (from {report.rows_in:,})",
        f"positives: {report.label_positives:,} ({report.label_rate:.4%})",
        "",
    ]
    lines += [f"WARNING: {w}" for w in report.warnings_]
    sidecar.write_text("\n".join(lines) + "\n")
    print(f"\nwrote {out}  ({len(panel):,} rows)")
    print(f"wrote {sidecar}")
    if args.source in ("emis", "oulad"):
        print(f"train with:  python -m edutrace.train.run --panel {out} "
              f"--out artifacts/model")
    else:
        print(f"train with:  python -m edutrace.train.enrolment --panel {out} "
              f"--out artifacts/enrolment")
    return 0


if __name__ == "__main__":
    sys.exit(main())
