# STATUS — read this before using anything in this repository

**Last updated:** 29 August 2026

## Where the model stands

There are now **two trained models** in `artifacts/`, and the difference
between them is the whole point.

| | `artifacts/oulad` | `artifacts/model` |
|---|---|---|
| Data | **REAL** — OULAD, 32,593 learners, CC-BY 4.0 | Simulated |
| Population | UK adults, distance learning | Synthetic Ghanaian JHS |
| Outcome | Real, dated course withdrawal | Generated |
| Held-out ROC-AUC | **0.726** | 0.827 |
| Calibration (ECE) | **0.0057** | 0.0028 |
| Precision @ top 0.5% | **36.3%** (6.5× lift) | 48.0% (35× lift) |
| Fairness gates | **All pass** (sex, deprivation, region, disability) | Sex gate fails |
| Validates | The methodology, on real people | The pipeline mechanics only |
| Safe to deploy on children | **No** | **No** |

**Neither model may score a real school learner.** The OULAD model is trained
on UK adults clicking in a virtual learning environment. The simulated model is
trained on data I generated. What has been established is that the machinery is
sound; what has not been established is that any of it predicts dropout among
Ghanaian children, because no data about Ghanaian children has ever entered it.

## What the OULAD run actually proved

Running the identical pipeline on 718,325 real learner-weeks confirmed:

1. **The discrete-time hazard label holds up on real event dates.** Positives
   precede their exits; administrative censoring removes every row without full
   follow-up; the transition is auditable from the panel.
2. **Isotonic calibration works at a real base rate.** ECE 0.0057 on a
   held-out period the model never saw — a stated 8% risk really is about 8%.
3. **The temporal split behaves as designed.** Forward-chaining shows
   ROC-AUC 0.63 → 0.72 → 0.72 as training data accumulates. A random split
   would have hidden this entirely.
4. **The model beats the transparent ABC rule at all four capacities**, which
   is the only comparison that justifies using a model at all.
5. **The fairness gates pass on real protected attributes** — sex, index of
   multiple deprivation, region, and disability — with FPR spread ≤ 0.0018 and
   worst calibration gap 0.0143.
6. **The domain guard works.** `StudentObservation` *refuses* OULAD rows,
   because they are 27–60-year-olds on modules called "AAA". That refusal is
   the schema doing its job, and cross-domain scoring goes through an explicit
   `score_vector` path instead.

### The most useful finding

**Real data scored lower than my simulator: 0.726 against 0.827.**

The simulator was easier than reality. That is the expected direction and it is
worth stating plainly, because it is the number most projects quietly avoid
producing. Any performance figure derived from synthetic data should be read as
an optimistic bound, not an estimate.

## What is ready

| | Status |
|---|---|
| Engineering architecture | **Ready.** ~11,000 lines, 106 tests passing |
| Evaluation methodology | **Validated on real data** (OULAD) |
| Explainability | **Ready.** TreeSHAP + counterfactual recourse, 2.1 ms/learner on real data |
| Safety gates | **Ready.** Human review, audit log, content filter, safeguarding, rule floor |
| Ingestion | **Ready.** OULAD proven end to end; DHS/MICS/Young Lives/EMIS written and fixture-tested |
| Model for Ghanaian JHS | **Does not exist** |
| Web UI / admin portal | **Does not exist** |
| Database | **Does not exist.** In-memory, wiped on restart |
| Authentication | Single shared API key, no per-school isolation |
| Deployment | No Docker, no CI |

## What would have to happen before this touches a child

1. Obtain data about the actual population — Ghana MICS/DHS for the annual
   enrolment model, school registers for the weekly triage model.
2. Retrain. Treat both current models as void for that purpose.
3. Validate against realised outcomes over at least one academic year.
4. Re-run the fairness audit on that cohort.
5. Replace the in-memory store with a database with per-school isolation.
6. Register with the Ghana Data Protection Commission; complete a DPIA.
7. Build the review interface — the human-review gate is a legal requirement
   under Act 843 s.41 and there is currently no screen for a teacher to use it.
8. Confirm support actually exists for the learners it flags.

## Limits that will not go away with more data

- At a low base rate, catching every at-risk learner means flagging most of the
  cohort. On OULAD at 7.8% base rate, 100% recall needs 89.7% of learners
  flagged at 8.7% precision. Perfect recall is arithmetically incompatible with
  useful triage — see the "without fail" section of the README.
- Prediction alone does not reduce dropout. Wisconsin's DEWS and Peru's Alerta
  Escuela both demonstrated this at national scale.
- A simple attendance-and-course-failure rule is a strong baseline. If a model
  does not clearly beat it on your data, ship the rule.

## Licence and provenance

Code is original, MIT licensed. OULAD is CC-BY 4.0 (Kuzilek, Hlosta & Zdrahal,
*Scientific Data* 4, 170171, 2017) and is **not** redistributed here — only the
adapter that reads it. No validated psychometric instrument is embedded, and
none may be added without a written licence.
