# EduTrace

> ### ⚠️ Two models here. Neither may score a real school learner.
>
> `artifacts/oulad` is trained on **real data** — 32,593 UK Open University
> learners, real dated withdrawals. It validates the *methodology*, not any
> claim about school children.
>
> `artifacts/model` is trained on a **simulator** and validates only the
> pipeline mechanics.
>
> No data about Ghanaian school children has ever entered either one.
> **Read [STATUS.md](STATUS.md) before using anything here.**

An early-warning triage system for junior high school attendance in Ghana.

Given a weekly record of a JHS learner, it estimates the probability that they
stop attending within the next eight weeks, ranks a cohort against the number
of conversations a school can actually hold, explains each estimate in plain
language, says what would have to change, and refuses to contact anyone until a
named member of staff has reviewed it.

```bash
pip install -e ".[dev]"
make simulate      # falsify the data generator against published Ghana statistics
make train         # temporal split, train, calibrate, evaluate, fairness gate
make demo          # end-to-end walkthrough
make test          # 106 tests
make oulad         # train on REAL data (OULAD)
make serve         # FastAPI on :8000
```

---

## The three claims this project is actually making

**1. The hard part is not the model.**  Every rigorous evaluation of a deployed
dropout early-warning system has found that prediction alone changes nothing.
Wisconsin's DEWS ran for a decade; the best available analysis could not rule
out zero effect on graduation. Peru's national *Alerta Escuela* reached every
school in the country and **7% of schools with flagged learners ever opened the
platform**; an SMS campaign raised platform usage and produced no increase in
preventive action and no reduction in dropout. So this codebase spends at least
as much effort on the review gate, the capacity-bounded worklist, the recourse
step and the call task as it does on the booster.

**2. An honest evaluation looks worse and is worth more.**  A random
train/test split on this panel would report a much higher AUC and mean nothing:
the same learner contributes ~120 autocorrelated weekly rows, and dropout
drivers shift year to year. Everything here is split strictly by academic year,
with a separate year for calibration, and the numbers quoted are
precision/recall at a capacity a school can staff — not accuracy, which is
99.2% for a model that predicts nobody ever leaves.

**3. Safety properties should be code, not documentation.**  A model card that
lists limitations nobody can enforce is decoration. Here the fairness gate
blocks the artifact write, the audit log raises on special-category fields, the
safeguarding record has no free-text field to put a disclosure in, the message
filter rejects the word "dropout", and the model refuses to load against a
mismatched feature contract.

---

## "Identify at-risk students without fail" — what that actually costs

This was the goal, and it is worth being precise about why it cannot be met and
what to do instead. Measured on this pipeline:

| recall target | must flag | % of cohort | precision | false alarms |
|---|---|---|---|---|
| 50% | 1,803 | 6.1% | 11.1% | 1,603 |
| 75% | 8,496 | 29.0% | 3.5% | 8,196 |
| 90% | 15,452 | 52.7% | 2.3% | 15,092 |
| **100%** | **26,181** | **89.2%** | **1.5%** | **25,782** |

To miss nobody you must flag 89% of the cohort. A school with one counsellor
holding twenty conversations a week has capacity for about twenty learners a
week. Handing it 26,181 names does not make the system safer — it ends triage,
and every child then receives an equal share of nobody's attention.

This is not a tuning problem. At a 1.4% base rate, perfect recall and useful
precision are mutually exclusive. Wisconsin's DEWS made exactly this trade,
explicitly accepting 25 false alarms per correct identification, and was wrong
about 74% of the learners it flagged — while its own equity review found the
false-alarm rate 42 points higher for Black students. Low-precision flooding
does not spread help evenly; it makes allocation arbitrary, and arbitrary
allocation lands hardest on the learners staff already overlook.

**The achievable version of the goal is different and better:** *no learner in
visible trouble is missed because a model ranked them low.* That needs no model
at all. `edutrace/triage.py` implements it as a three-part structure:

- **FLOOR** — rare, severe, published thresholds. Absent eight days straight;
  attendance collapsed below 35%; JHS3 Term 3 with no BECE registration.
  Tripping one puts a learner on the list regardless of model score, and each
  is verifiable by hand from the register.
- **RANK** — the model orders everyone else, the learners whose risk is *not*
  visible on the face of the register. That is the only place a model adds
  anything over a rule.
- **ACCOUNT** — every run publishes what the combined system missed and what
  the misses look like, so blind spots are declared rather than discovered.

### The floor bit me first, which is the point

My first floor used sensible-sounding thresholds — under 80% attendance, two
core failures, two terms of levies owed. Measured, they fired on **64%, 35% and
35%** of the cohort. Combined, 73% of learner-weeks were escalated, the
worklist filled with floor cases before the model got a slot, and recall at
fixed capacity fell to **22.1% against the model's own 25.6%**. The safety net
made the system worse, in precisely the way the paragraphs above warn about.

So `Floors.validate()` now enforces a trip-rate budget and fails loudly when a
rule exceeds it, capacity is split between floor and model rather than given to
the floor outright, and the worklist deduplicates to learners rather than
learner-weeks. A test asserts the combined system never catches fewer than the
model alone.

A realistic weekly run — 836 learners, capacity 20:

```
caught by floor       2   transparent rules, no model involved
caught by model       0   ranked into the remaining slots
caught in total       2   recall 16.7%
model alone would     1   (floor helps)
MISSED               10   83.3% of learners who left

Miss profile (missed learners vs whole cohort):
                                        missed    cohort
    attendance_rate_term_to_date         51.78     68.87
    consecutive_absences                  2.30      1.61
    fee_arrears_terms                     2.10      1.36
```

16.7% recall is the honest number, and the miss profile is the useful part: the
misses are learners at 52% attendance with levy arrears — not invisible, just
outranked by learners in worse shape. The route that actually reduces misses is
more capacity or better signal, not a lower threshold.

---

## Validated on real data: OULAD

The identical pipeline, run on the [Open University Learning Analytics
Dataset](https://analyse.kmi.open.ac.uk/open_dataset) — 32,593 real learners,
10.6M timestamped interactions, real dated course withdrawals, CC-BY 4.0.

```bash
python -m edutrace.ingest.cli convert oulad /path/to/oulad --out data/oulad.csv
python -m edutrace.train.run --panel data/oulad.csv --out artifacts/oulad \
    --protected sex,poverty_quintile,region,disability
```

718,325 learner-weeks, 5.60% positive rate, four course presentations split
strictly by time. Held-out period 2014J, never seen in training or calibration:

| | |
|---|---|
| ROC-AUC | **0.726** |
| PR-AUC | 0.147 |
| Brier | 0.0500 |
| Expected calibration error | **0.0057** |

| capacity | precision | recall | lift |
|---|---|---|---|
| top 0.5% (1,252) | **36.3%** | 3.3% | 6.5× |
| top 1% (2,504) | 30.5% | 5.5% | 5.5× |
| top 2% (5,009) | 24.6% | 8.8% | 4.4× |
| top 5% (12,524) | 19.2% | 17.3% | 3.5× |

Forward-chaining, each fold trained only on prior presentations:

```
train 2013B      -> test 2013J    ROC-AUC 0.632
train 2013B-J    -> test 2014B    ROC-AUC 0.716
train 2013B-2014B-> test 2014J    ROC-AUC 0.715
```

Unseen modules (group-split): 0.701–0.735. Beats the ABC rule at 4/4
capacities. **All fairness gates pass** — sex, index of multiple deprivation,
region and disability, with FPR spread ≤ 0.0018.

Serving on real data: **2.1 ms per learner** with full TreeSHAP explanation and
counterfactual recourse; 50,000 learner-weeks scored in 0.10 s.

### The finding worth reporting

**Real data scored lower than the simulator: 0.726 against 0.827.**

The simulator was easier than reality. That is the expected direction, and it
is the number most projects quietly avoid producing. Treat any metric derived
from synthetic data as an optimistic bound.

### What OULAD does and does not license you to claim

It **does** establish that the discrete-time hazard label holds on real event
dates, that administrative censoring is applied correctly, that isotonic
calibration works at a real base rate, that the temporal split reveals drift a
random split would hide, and that the fairness gates operate on real protected
attributes.

It establishes **nothing** about Ghanaian junior high school. OULAD is UK
adults; "attendance" is a click-based proxy; fees, distance, child labour,
guardian structure and behaviour records do not exist in it. The domain guard
enforces this — `StudentObservation` *rejects* OULAD rows outright, and
cross-domain scoring must go through the explicit `score_vector` path.

---

## The simulated model, for comparison

Trained on **simulated** data, 3,600 learners, 415k weekly observations, six
academic years, 0.77% positive rate. Held-out year 2026:

| | |
|---|---|
| ROC-AUC | 0.827 |
| PR-AUC | 0.231 |
| Brier | 0.0116 |
| Expected calibration error | 0.0028 |

Capacity metrics — what a school actually experiences:

| capacity | precision | recall | lift vs random |
|---|---|---|---|
| top 0.5% (146 learners) | 0.480 | 0.175 | **35×** |
| top 1% (293) | 0.382 | 0.281 | 28× |
| top 2% (586) | 0.234 | 0.343 | 17× |
| top 5% (1,467) | 0.125 | 0.459 | 9× |

Forward-chaining validation, each fold trained only on prior years:

```
train 2021      -> test 2022    ROC-AUC 0.776   P@1% 0.017
train 2021-2022 -> test 2023    ROC-AUC 0.835   P@1% 0.061
train 2021-2023 -> test 2024    ROC-AUC 0.835   P@1% 0.159
train 2021-2024 -> test 2025    ROC-AUC 0.795   P@1% 0.167
train 2021-2025 -> test 2026    ROC-AUC 0.833   P@1% 0.399
```

The dip at 2025 is not noise. The simulator embeds an economic shock in that
year — levy arrears rise and their association with leaving strengthens. A
random split hides this completely. Real deployments meet it every year.

Held-out schools (and therefore held-out regions) score ROC-AUC 0.833–0.839,
so the model transfers to institutions it has never seen.

### It has to beat the rule, and it is checked every run

The ABC framework — Attendance, Behaviour, Course performance — is the
benchmark, not a courtesy. Chicago's Freshman On-Track *rule* drove system-wide
graduation gains, and REL Mid-Atlantic found an ML model with child-welfare and
justice-system data only "similarly accurate" to a prior-performance rule at
matched flag rates. Every training run prints:

```
capacity      model P   rule P   model R   rule R       ΔR   verdict
top 0.5%       0.4795   0.3151    0.1754   0.1153   +0.0602  model
top 1%         0.3823   0.2048    0.2807   0.1504   +0.1303  model
top 2%         0.2338   0.1433    0.3434   0.2105   +0.1328  model
top 5%         0.1247   0.0682    0.4586   0.2506   +0.2080  model
```

If the rule wins, ship the rule. It explains itself, costs nothing to serve,
and cannot hide a protected attribute.

---

## The fairness gate, and the failure it caught

`make train` currently **refuses to write the artifact**. This is the system
working, and it is the most interesting result in the project.

```
fairness by sex   FPR spread 0.0045 (<= 0.05) | recall spread 0.2420 (<= 0.15)
                  | worst calib gap 0.0047 (<= 0.02)                    [FAIL]

   group        n     pos   flag   recall    prec      FPR   calib gap
   F       14,832     200     91    0.160   0.352   0.0040     -0.0047
   M       14,510     199    202    0.402   0.396   0.0085     -0.0006
```

Girls and boys have effectively identical base rates — 200 versus 199 exits —
and the model finds **40% of the boys and 16% of the girls**. `sex` is not a
model input; the disparity is entirely mechanical. In the simulator, boys' exits
are driven by paid and farm work, which produces a gradual, weeks-long
attendance decline the model reads easily. Girls' exits are driven
disproportionately by pregnancy, which produces a sharp late absence spike the
model only sees days before departure. A model blind to sex still fails girls,
because the *signal* arrives later for them.

That is the whole argument for auditing outcomes rather than sanitising inputs.
Wisconsin's DEWS is the cautionary case: an internal 2021 analysis found its
false-alarm rate 42 percentage points higher for Black students than White
students, concluded "Is DEWS Fair? … no", and the system ran unchanged and
undisclosed to districts. Nothing in that pipeline could stop it. Here,
something can, and the remediation options are printed with the failure:

1. Fix the feature set — add earlier signals for the pathway being missed
   (health-related absence patterns, a pastoral flag), which is the real fix.
2. Lower the capacity; a tighter flag set usually narrows the spread.
3. Post-process toward equal opportunity and accept the precision cost.
4. `--allow-unfair`, which writes the artifact **with the failure recorded on
   the model card** and served at `/model-card`.

Note what is *not* gated: recall parity across poverty quintiles, where base
rates differ 25×. Calibration-within-group and equal recall are mathematically
incompatible at unequal base rates (Kleinberg et al.; Chouldechova), so demanding
equal recall there would mean flagging better-off learners who are not at risk in
order to level a statistic. Recall parity is a hard gate only where base rates
are comparable; **calibration-within-group and false-positive-rate parity are
hard everywhere**, because those two cannot be explained away by base rates —
and they are the two DEWS failed.

---

## What changed from the original brief

| Proposed | What ships | Why |
|---|---|---|
| Gender as a model input | **Protected attribute, audit-only.** Mechanisms captured instead (pregnancy-related absence, care duties, work) | Feeding sex/race/income to the model is the DEWS failure exactly. It cost 42pp of false-alarm parity there |
| "Fully / half / partially paid" | `EXEMPT / PAID_IN_FULL / PART_PAID / UNPAID` | Two of the original levels overlapped, and none expressed capitation-grant coverage — the common case in Ghanaian public JHS |
| Raw exam score out of 100 | **Within-school-within-grade percentile** | A 62 at one school is not a 62 at another. Marking cultures differ more than pupils do |
| Flat "is a dropout" label | **8-week discrete-time hazard**, with administrative censoring | A flat label leaks the future and cannot be acted on in week 3. Rows without full follow-up are *dropped*, not labelled zero |
| Behavioural flag (none/minor/serious) | Kept for compatibility, **weighted down**, structured items preferred | A single subjective flag is the feature most likely to encode a teacher's opinion of a child rather than the child's behaviour |
| Risk threshold as a fixed percentage | **Capacity-based tiers** (quantiles of the score distribution) | A fixed 0.7 cutoff on a calibrated probability at a 0.8% base rate flags nobody, ever |
| Teacher-run psychometric evaluation | **Structured supportive conversation** producing a needs profile, not a score | See below — this one is not negotiable |
| SMS alerts as the intervention | SMS **plus a tracked call task** at HIGH tier | The Botswana RCT: SMS alone d=0.024, p=0.60 (a precise zero); SMS + weekly call d=0.121, p=0.008 |
| — | Added: over-age gap, repetition, absence streaks and trend, assessment completion, textbook/uniform possession, BECE registration | Ghana's JHS GER is 85% against NER 45% — over-age enrolment is roughly half the cohort and is a strong signal |

### The psychometric module, specifically

You asked for a teacher-administered psychometric evaluation for flagged
learners. I did not build it, and I would push back on building it at all.

- **Licensing.** The Student Engagement Instrument is free "for research or
  practice" but explicitly "not for purposes resulting in profit". The SDQ
  states users "are not permitted to create or distribute electronic versions
  for any purpose without prior authorization from youthinmind" — a digital
  product *is* an electronic version. RCADS forbids commercial distribution of
  the instrument or derivatives. PSSM requires the author's permission. BASC-3
  BESS and BIMAS-2 are per-administration licensed and US-normed.
- **Scope of practice.** Ghana has a Psychology Council (Act 857). A teacher
  administering something the software calls a psychometric evaluation, and
  scoring a child on it, is practising psychology.
- **Norms.** A scoping review of SDQ use across Africa found the instrument
  widely used and its psychometric properties in African settings largely
  unestablished. UK cut scores on Ghanaian JHS learners produce confident
  numbers that mean nothing.
- **No screening without services.** The uniform bright line in school
  psychology guidance. Absent a real pathway to support, flagging a child is not
  a benefit; it is a labelling harm.

What ships instead is a structured supportive conversation: WHO Psychological
First Aid's Look/Listen/Link (explicitly designed so "it is not necessary to
have a 'psychosocial' background"), a motivational-interviewing stance, and
Check & Connect's mentor pattern — nine open questions across eight barrier
domains, each mapped to a support a Ghanaian JHS could actually mobilise. The
output is a **needs profile**, never a score, and it **does not change the risk
estimate**. Two channels stay separate: the actuarial estimate says who to look
at, the conversation says what to do. Blending teacher perception into the model
creates a loop where the model's ground truth becomes the teacher's opinion.

If staff disagree with a tier, that goes through a **bounded, reason-coded
override** — one step, from a fixed reason list, logged so override accuracy can
be audited by group annually. The risk-assessment literature is clear that
unbounded clinical override degrades accuracy and encodes bias.

The teacher-training layer you wanted is real and worth building — but from
INEE's *Training Pack for Primary School Teachers in Crisis Contexts* and
UNICEF's MHPSS guidelines, which are openly licensed and built for exactly this
setting. Not invented here.

---

## Architecture

```
edutrace/
  contract.py          Feature contract: the single source of truth. 32 features,
                       ordered, fingerprinted. Protected attributes and PII are
                       declared out of it, and a test enforces that.
  records.py           Pydantic I/O. PII lives on a separate model that never
                       reaches the feature builder.
  features.py          ONE feature implementation. build_frame (vectorised) and
                       build_row (row-wise, no pandas) must agree bit-for-bit;
                       tests/test_invariants.py::test_no_train_serve_skew proves it.

  simulate/            Structural causal model of Ghanaian JHS attrition.
    targets.py         Published statistics with sources and tolerances.
    generator.py       The DAG, sampled forward. Two-pass hazard calibration.
    validate.py        Falsifies the generator against targets.py. 8/8 pass.

  train/
    splits.py          Forward-chaining by year; group-by-school.
    model.py           XGBoost + isotonic calibration + monotonic constraints,
                       tier thresholds, probability bounds, model card.
    evaluate.py        precision@k, recall@k, calibration, fairness reports.
    baseline.py        The ABC rule the model must beat.
    run.py             The pipeline, with the fairness gate.

  explain/
    attribution.py     TreeSHAP via native pred_contribs, themed and filtered.
    recourse.py        Counterfactual bisection on the raw margin.
    narrative.py       Deterministic plain-language templates. No LLM.

  serve/
    scorer.py          Hot path. ~7 ms with full explanation.
    review.py          The human-review gate and bounded override.
    audit.py           Append-only JSONL that refuses special-category fields.
    app.py             FastAPI.

  conversation/
    protocol.py        The support conversation. Read its docstring.
    safeguarding.py    Escalation records with no free-text field, by design.

  messaging/
    encoding.py        GSM-7 vs UCS-2 and the Ghanaian-orthography trap.
    templates.py       Guardian messages: facts and invitations only.
    dispatcher.py      Tier-based channel escalation and the content filter.
    providers/         Console (default), Arkesel; abstracted from day one.
```

### Performance

| operation | measured |
|---|---|
| single score, no explanation | **0.35 ms** |
| single score + TreeSHAP + recourse + narrative | **7 ms** |
| batch scoring, 10,000 rows | **< 1 s** (2 vCPU) |

The choices that account for it, and why:

- **`inplace_predict`, not `DMatrix` + `predict`.** DMatrix construction is
  historically 45–90% of predict time; on a single row it is ~1.9 ms versus
  ~0.7 ms.
- **`nthread=1` on the request path.** At batch size 1 thread coordination costs
  more than the work. Bulk scoring temporarily takes every core.
- **`max_depth=6` is a latency budget, not just regularisation.** TreeSHAP cost
  grows roughly with depth squared: published figures put depth-4 at ~0.24
  ms/row and depth-12 at ~48 ms/row. Depth 6 is what makes "every score ships
  with its explanation" affordable.
- **Explanations are computed for the top-k only** in batch mode. Explaining
  10,000 rows would cost ~30 s in TreeSHAP, and no school will read 10,000
  explanations — it will read the ones it has capacity to act on.
- **Recourse runs only at ELEVATED and above.** For a LOW-tier learner there is
  nothing to recommend, and 5 ms to discover that is waste.

Framework choice is not the bottleneck: FastAPI costs ~43 µs of CPU per
request while inference costs 350–7,000 µs. Switching `predict` →
`inplace_predict` bought ~1,200 µs; rewriting in Go would buy ~30 µs.

---

## Four bugs worth reading about

Each of these produced a plausible-looking system that was quietly wrong. Each
now has a test.

**Train/serve skew in the attendance trend.** The simulator emitted a two-point
slope; `build_row` computed a least-squares slope. Nothing crashed. A textbook
high-risk profile simply ranked about ten percentiles too low, and would have
gone unflagged. `test_no_train_serve_skew` compares all 32 features across both
paths, including NaN patterns.

**Isotonic plateaus destroyed the counterfactual search.** Recourse originally
bisected on the calibrated probability. Isotonic regression is a step function,
and at a sub-1% base rate its upper region is a few very wide plateaus — so the
system reported that raising a learner's four-week attendance from 30% to 70%
changed the risk by *exactly nothing*. Not indifference: both values landed on
the same step. The search now runs on the smooth raw margin and converts back
only for display.

**Incoherent counterfactuals.** Setting `attendance_rate_last_4w` to 70 while
`attendance_rate_term_to_date` stayed at 20 describes a learner who cannot
exist, in a region the model has never seen. Levers are now *bundles*: one
scalar a school can influence, plus arithmetic propagation to everything that
moves with it (term-to-date attendance is a running mean, so it shifts by
`4·Δ/weeks_elapsed`).

**Non-monotonic response to attendance.** Predicted risk at 60% attendance sat
*above* risk at 40%, because that region is thinly populated and the trees fit
noise. This invalidates the recourse bisection, makes the explanation nonsense
to a teacher, and is indefensible in review. Fixed with XGBoost
`monotone_constraints` on the 25 features whose causal sign is genuinely known —
which also improved precision@0.5% from 0.40 to 0.48.

Two more the calibration harness caught: the hazard intercept was centred on
`E[η]` instead of `log E[e^η]`, overshooting the target annual dropout rate 5×
(Jensen); and the first coefficient set spanned 10 log-odds — a 22,000× hazard
ratio between the safest and most precarious child — which is not a thing that
happens in education data, and which collapsed the simulation so that pregnancy
alone accounted for 82% of girls' exits.

---

## Training on real data

`edutrace/ingest/` converts real sources into trainable panels. The path is
built, tested end to end, and waiting on files only you can download — every
relevant dataset is behind a registration that has to be completed in your own
name, and this environment has no network egress.

### There are two models here, and only one is publicly trainable

| | Model B — weekly triage | Model A — annual enrolment |
|---|---|---|
| **Question** | who should the counsellor see on Tuesday? | who is at risk of not returning next year? |
| **Unit** | learner × week | child × school year |
| **Needs** | attendance registers, assessments, levy ledger | household survey |
| **Source** | a partner school / GES EMIS | Ghana MICS, Ghana DHS |
| **Public data exists?** | **No. Anywhere.** | **Yes, free, for Ghana** |
| **Contract** | `edutrace.contract` (32 features) | `ingest.base` (19 features) |
| **Trainer** | `edutrace.train.run` | `edutrace.train.enrolment` |

Attendance registers do not leave schools, so no public dataset on earth
contains Model B for Ghanaian JHS. Model A is genuinely obtainable in weeks and
is what makes a *locally credible Ghanaian* model possible now. It cannot do
weekly triage — it has no attendance — but it does three real things: it
targets enrolment and re-entry campaigns between school years; it replaces the
hand-written coefficients in the simulator with real Ghanaian effect sizes; and
it is the honest interim while a partner school accumulates register data.

The two carry **separate contract fingerprints** so they cannot be confused at
serving time. A model trained where attendance is always missing never learns
to use attendance, and would then ignore the strongest signal in the file the
moment it appeared — so the enrolment model is refused as a weekly model rather
than silently loaded.

### Getting Ghanaian data (Model A)

1. **Ghana MICS 2017/18** — the most locally credible option. Register at
   <https://mics.unicef.org/surveys> with a short statement of purpose; free.
   Also take the **MICS GIS cluster release**, which lets you compute real
   distance-to-school by joining cluster centroids to a school layer.
2. **Ghana DHS 2022** — <https://dhsprogram.com> (per-project registration) or
   <https://microdata.statsghana.gov.gh/index.php/catalog/123>. The household
   member recode carries the school transition directly in HV121–HV126.
3. **GLSS 7** — <https://microdata.statsghana.gov.gh/index.php/catalog/97>.
   The best Ghanaian source for household schooling *expenditure*, which is the
   real proxy for the levy-burden feature.
4. **Young Lives** (SN 9543, UK Data Service, free with registration) — not
   Ghana, but a genuine longitudinal enrolled→left transition across ages
   12–15. Use it to show the approach recovers real effect sizes on real
   children of the right age, then localise with MICS/DHS.

Then:

```bash
# 0. Rehearse the whole path on a survey-shaped fixture (no real data needed)
make ingest-demo

# 1. ALWAYS check the transition crosstab first
python -m edutrace.ingest.cli check dhs GHPR8AFL.DTA

# 2. Convert. Refuses to write if the quality gates fail.
python -m edutrace.ingest.cli convert dhs GHPR8AFL.DTA --out data/ghana_dhs.csv

# 3. Train the annual model on real Ghanaian data
python -m edutrace.train.enrolment --panel data/ghana_dhs.csv --out artifacts/enrolment
```

Step 1 is not optional. DHS variable numbering shifts between phases and MICS
between rounds. Note that **HV121–123 are the CURRENT year and HV124–126 the
PREVIOUS year** — it is commonly miscited the other way round, which inverts
the label and produces a confident, backwards model that every downstream
metric will happily bless. The crosstab catches it in one glance. If your
columns differ, `python -m edutrace.ingest.cli template dhs --out map.json`
writes a starter map to edit and pass with `--map`.

The ingest refuses to emit a panel it cannot vouch for: under 500 rows, under
50 positives, or a label rate above 40% (which nearly always means an inverted
transition or a missing age filter) block the write. It also reports per-feature
support, because DHS has no distance-to-school or child-labour module in the PR
file and you should know that before you rely on those columns rather than
after.

Verified end to end on a DHS-shaped fixture with real variable names:

```
rows in 10,284 -> rows out 4,114 -> 267 positives (6.5%)
head_education_years  100%   (derived across household members)
siblings_in_school    100%   (derived across household members)
distance_band_ord       0%   <-- unusable, DHS PR file has no distance
ROC-AUC 0.611 on a held-out split
```

0.61 is the realistic range for annual household-survey dropout prediction —
the literature sits at 0.62–0.85, and enrolment-time-only models around
0.66–0.78. Anything near 0.99 means leakage.

### Getting register data (Model B)

Only a partner school or GES EMIS. `ingest/emis.py` takes either daily or
weekly registers and derives the rolling rates, streaks, trends and the 8-week
label *identically to the feature builder*, so nothing is computed in a
spreadsheet first — that is how train/serve skew gets in.

```bash
python -m edutrace.ingest.cli convert emis register.csv --daily --out data/school.csv
python -m edutrace.train.run --panel data/school.csv --out artifacts/model
```

Before you start, agree the exit definition with the school **in writing**.
"Stopped attending" is a decision, not a fact: the default is four consecutive
weeks with no attendance and no return before the window closes. Transfers are
excluded from the panel entirely rather than labelled zero — their outcome is
unobserved, and counting a transfer as a non-event teaches the model that
leaving quietly is safe.

---

## Data: the simulator, and why it is still here

**The model currently ships trained on simulated data, and every number above
describes the pipeline, not Ghanaian children.** The generator is a structural
causal model, not random noise — poverty drives levy arrears and child work,
those drive absence, absence drives exam collapse, and the chain ends in a
learner leaving — and it is *falsifiable*: `make simulate` checks it against
eight published statistics and currently passes all eight.

```
[PASS] dropout_annual_rate                 0.0411  vs 0.04  ± 0.012
[PASS] dropout_ratio_poorest_to_richest    10.46   vs 9     ± 3.5
[PASS] dropout_ratio_male_to_female         1.087  vs 1.5   ± 0.5
[PASS] share_over_age                       0.554  vs 0.53  ± 0.1
[PASS] repetition_rate                      0.137  vs 0.105 ± 0.035
[PASS] share_within_short_walk              0.511  vs 0.528 ± 0.1
[PASS] jhs3_share_of_all_exits              0.598  vs 0.45  ± 0.15
[PASS] female_exits_attributable_to_pregnancy 0.311 vs 0.28 ± 0.15
```

Sources are in `edutrace/simulate/targets.py`: the MoE/GPE Ghana Partnership
Compact 2023, the CGD/IEPA PREPARE household survey (March 2021), and the 2021
Population and Housing Census proximity report.

**But matching marginals is necessary, not sufficient.** A generator can
reproduce every mean and correlation in that table while getting the conditional
structure wrong. Any feature-importance plot from this model is a readout of the
hand-written coefficients in `generator.py`. The AUC is evidence that the
pipeline works; it is not evidence that the predictor works.

To make it real, in order of effort:

1. **Young Lives** (UK Data Service, free with registration) — 12,000 children
   across four countries followed since 2001, ages 8–15+, with a true
   longitudinal enrolment→dropout label plus prior grades, household poverty and
   shocks. Rounds 1–7 constructed files: SN 9543. No Ghana, but the right ages
   and a real outcome.
2. **Ghana MICS 2017/18** (UNICEF/GSS, free with registration) plus the **MICS
   GIS cluster release**, which allows real distance-to-school by joining cluster
   centroids to a school layer. Dropout is derived the way UIS derives it:
   attended-this-year × attended-last-year × grade-last-year.
3. **Ghana DHS 2022** — household recode variables HV121/HV122/HV125/HV126 give
   a ready-made one-year school transition per household member.
4. **GLSS 7** — the best Ghanaian source for household schooling *expenditure*,
   which is the real proxy for the levy-burden feature.
5. **A partner school.** `--panel your.csv` takes a real panel directly. The
   label must be built the same way: an 8-week forward hazard with
   administrative censoring applied.

Do not use the UCI "Predict Students' Dropout and Academic Success" dataset as
though it were secondary-level — it is tertiary, Portuguese, and the only
mainstream open dataset carrying a fee-payment feature, which is why it gets
miscited constantly.

---

## Deployment reality

**SMS economics.** Twilio charges ~$0.374 per outbound segment to Ghana; local
aggregators sit near GHS 0.02–0.03 (~$0.002). At 500,000 alerts a year that is
roughly $800 locally against ~$187,000 on global CPaaS. There is no version of
this product where a global CPaaS is the primary route. Providers are abstracted
from day one because per-carrier rates and delivery quality differ enough that
route-switching is a live operational lever.

**The orthography trap.** Twi needs `ɛ ɔ`, Ewe needs `ɖ ƒ ŋ ʋ`, Dagbani needs
`ɣ ŋ ʒ`. One such character forces the *entire* message to UCS-2, cutting the
segment from 160 characters to 70 — a ~3× cost multiplier on the highest-volume
thing the product does, and unreliable rendering on feature phones.
`messaging/encoding.py` transliterates for SMS and keeps true orthography for
voice and the web UI. Every template is checked to fit one segment at startup;
the check caught a real 165-septet overrun during development.

**Act 843 shapes the architecture, not just the privacy policy.**

- *s.37* — data on a child under parental control is **special personal data**.
  The whole dataset is special-category by default.
- *s.41* — a data subject may require that a significant decision not be made
  solely by automatic means. A dropout flag that texts a guardian is exactly
  that, which is why the human-review gate is a legal control rather than a UX
  preference.
- *s.62* — pupil data held by an educational institution may not be disclosed
  except where required by law. Every onward disclosure needs a documented basis
  in the school contract.
- Registration as a data controller is mandatory before processing (s.27, s.53).
- A breach triggers **two** clocks: Act 843 s.31 ("as soon as reasonably
  practicable") and the Cybersecurity Act 2020 s.1038's 24-hour CERT
  notification.
- Build to the pending Data Protection Bill 2025 (parental consent, DPIAs,
  72-hour breach notice, explicit automated-decision duties), not to Act 843
  alone.

**Hosting.** Measured RTT from Accra: Cape Town 65 ms, Johannesburg 88 ms,
London 96 ms, Dublin 112 ms, Frankfurt 123 ms. AWS `af-south-1` beats every
European region — Equiano and WACS run down the west coast. There is no
data-localisation requirement for education data (the Bank of Ghana rule is
financial-sector only), so `af-south-1` primary with a European warm standby is
both faster and more defensible. The March 2024 quadruple cable cut, which took
five weeks to repair, is the argument for multi-region rather than local colo.

**Connectivity.** Assume under 25% of basic schools have internet — UNESCO's
last Ghana figure is 23%, and Eduwatch found 21 of 1,033 deprived-district
schools with a functional ICT lab. Budget under 1 MB first load. Do not build
the sync guarantee on the Background Sync API; it is Chromium-only. Use a
durable IndexedDB outbox flushed on `online`/`visibilitychange`.

---

## What this is not for

Served at `/model-card` and enforced by review, not by hope:

- Any decision about a child taken without a named member of staff reviewing it.
- Streaming, setting, exclusion, disciplinary action, or exam-entry decisions.
- Sharing a risk score with the learner, or outside the pastoral chain.
- Ranking schools, teachers, or districts.
- **Any deployment where no support is actually available to the learners it
  flags.** Screening without services is a labelling harm, not a benefit — and
  it is the failure mode that made Peru's national system worthless.

---

## Before a real learner is scored

- [ ] Retrain on real data; treat every number in this README as void
- [ ] Re-validate the tier thresholds against realised local outcomes
- [ ] Replace the in-process `Store` with Postgres, row-level security per school
- [ ] Register with the Ghana Data Protection Commission; complete a DPIA
- [ ] Get transactional (not promotional) traffic classification in writing from
      the SMS aggregator
- [ ] Register the sender ID with MTN — allow ~2 weeks
- [ ] Agree the safeguarding escalation contacts with the district G&C coordinator
- [ ] Train staff on the review gate before turning notifications on
- [ ] Set the annual re-validation date, and the date the fairness audit is
      re-run against realised outcomes by sex, region and school
