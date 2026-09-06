# Student CSV format

Choose a class before importing. The first row must contain headers. The
official template is available from the teacher Imports page or
`GET /api/v1/imports/template`.

This roster endpoint uses the onboarding schema `studentName,gradeLevel,
externalId,guardianName,guardianMsisdn,attendanceRateTermToDate,
attendanceRateLast4w,avgExamScore,assessmentCompletionRate,
coreSubjectFailures,feeStatus,hasTextbooks,hasUniform,doesPaidOrFarmWork,
distanceBand`. Only `studentName` and `gradeLevel` are required. Extra columns
are ignored. Percentages and scores use 0-100; values from 0 to 1 are treated
as fractions, and booleans accept `true`/`false`, `1`/`0`, or `yes`/`no`.

This onboarding route writes the current calendar year, `T1`, and week `1`.
The separate ML batch-scoring endpoint owns the full Python
`StudentObservation` schema and weekly updates.

Download the template rather than copying a shortened schema. It includes safe
`DEMO-001` and `DEMO-002` identifiers and blank guardian phone numbers.

Supported roster values are grades `JHS1`-`JHS3`, fee statuses `EXEMPT`,
`PAID_IN_FULL`, `PART_PAID`, `UNPAID`, and distance bands `UNDER_15_MIN`,
`M15_TO_30`, `M30_TO_60`, `OVER_60_MIN`.
Do not include safeguarding disclosures, free-text narratives, or unnecessary
medical information in the CSV.

The import workflow will validate headers, values, duplicates, and row errors
before writing students or observations. Never upload real data into the demo
environment.

## Batch scoring from the teacher workspace

The Imports page also provides **Run risk analysis** for the model-shaped CSV.
It calls the authenticated Node proxy:

```text
POST /api/v1/predictions/batch?capacity=40
```

Send the file as multipart field `file`. Required model columns are
`student_key`, `school_id`, `academic_year`, `term`, `week`, and `grade_level`.
The API checks that each row belongs to the signed-in teacher's school or
school code, then forwards the raw CSV to the Python model service. The
capacity controls the size of the returned follow-up worklist; it does not
change the model score.
