# EduTrace

A school early-warning and student-support platform for Ghanaian JHS. This
repository is a monorepo with three deployable pieces plus a shared database
schema.

```
edutrace-platform/
├── apps/
│   ├── api/            Node.js/Express backend (JavaScript, ESM, NOT TypeScript)
│   └── web/             Next.js frontend (built in a later phase)
├── services/
│   └── ml/               FastAPI wrapper around the vendored edutrace Python package
│       ├── vendor_edutrace/            the supplied edutrace-v0.2.0 package, unmodified
│       ├── vendor_edutrace_artifacts/  the two supplied model bundles (oulad, model)
│       ├── app/                        the thin production wrapper (auth, our routing)
│       └── STATUS.md                   copied verbatim from the supplied repo — read this
├── packages/
│   └── db/                Prisma schema + migrations, shared source of truth for the DB
└── docs/                  Architecture notes, phase plan, model governance policy
```

## Why the ML service is "vendored, wrapped" rather than rewritten

`services/ml/vendor_edutrace` is the **unmodified** Python package from
`edutrace-v0.2.0.zip`. Nothing in it is rewritten. `services/ml/app` is a thin
FastAPI layer that:

1. Adds service-to-service authentication (a shared HMAC-signed header, not the
   demo `X-API-Key`) so the ML service is never reachable except from the Node
   API.
2. Re-exports the existing `edutrace.serve.app` routes largely as-is — scoring,
   explanation, recourse, review, notify, safeguarding, conversation — because
   that logic (the banned-phrase filter, the review gate, the safeguarding
   referral checklist) is safety-critical and already correct. Duplicating it
   in Node would be the exact anti-pattern the project brief warns against.
3. Adds `/internal/v1/models/active` and `/internal/v1/models/:version`,
   thin reads over the existing `ModelBundle`/`ModelCard`, used by Node's
   model governance registry (see below) rather than by end users directly.

**What stays in-memory vs. what moves to Postgres:** the supplied
`serve.app.Store` (assessments, reviews, guardian numbers, school index) is
process-local and wiped on restart — correct for a demo, wrong for production,
as `STATUS.md` says explicitly. Node owns the durable copy: every response
from the ML service is persisted to Postgres by Node before it reaches a
client. The ML service itself remains stateless per request wherever
practical; its own `Store` is left as an internal cache, not the system of
record.

## Model governance (the part the supplied repo doesn't enforce yet)

`STATUS.md` is unambiguous: **neither supplied model may score a real
learner.** The supplied `ModelCard` has no machine-checkable status field —
that determination lives in a markdown file, not in code that can refuse a
request. This platform adds that enforcement in Node, not Python:

- `packages/db/prisma/schema.prisma` defines a `ModelRegistration` table:
  `modelVersion`, `contractFingerprint`, `dataProvenance`, `status`
  (`DEVELOPMENT | VALIDATION | APPROVED | ACTIVE | RETIRED`), `approvedBy`,
  `approvedAt`, plus the evaluation metrics pulled verbatim from the model's
  own `/model-card` response.
- Every model version the ML service reports is auto-registered as
  `DEVELOPMENT` on first sight. It never becomes `ACTIVE` without a
  `SYSTEM_ADMIN` explicitly approving it through the admin API, which requires
  the admin to have read a rendered version of the model's own limitations.
- The scoring endpoints in Node (`POST /api/v1/schools/:id/predictions`, etc.)
  check the registry **before** calling the ML service. If there is no
  `ACTIVE` model, real scoring is refused with a clear error. A separate,
  clearly-labelled **demo mode** endpoint exists for development, which is
  wired to accept only non-production school records (seeded fixtures) and
  stamps every response with `"demo": true` and the model's own
  `DO_NOT_USE_ON_REAL_LEARNERS` limitation text where present.

Given both supplied models (`oulad`, `model`) are explicitly unsafe for real
Ghanaian learners per `STATUS.md`, the registry seeds both as `DEVELOPMENT`
and neither is pre-approved. The system will refuse real scoring out of the
box until an admin trains/validates a real model and approves it — this is
intentional, not a bug to "fix" by pre-approving something.

## Run locally

See [docs/LOCAL_DEVELOPMENT.md](docs/LOCAL_DEVELOPMENT.md) for Docker and
process-based startup. The development bootstrap command creates the first
school and system administrator, then prints the school code teachers use at
`/register`.

See [docs/csv-format.md](docs/csv-format.md) for the student CSV headers and
sample rows.

## Phase status

See `docs/PHASE_PLAN.md`. This commit delivers **Phase 1 (repo/architecture)**
and **Phase 2 (database schema)**.

## Create New School

npm run create:school --workspace=@edutrace/api -- \
 --name="ABC Junior High" \
 --code=ABC-JHS \
 --district=Accra \
 --region=Greater-Accra \
 --admin-email=admin@example.com \
 --admin-password="change-this-password"

# TEST

School ID: cmtp06rsf0001i98ua86qmop2
