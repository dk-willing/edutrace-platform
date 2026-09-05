# Architecture

## Services

| Service | Tech | Responsibility |
|---|---|---|
| `apps/web` | Next.js/React | Teacher, admin, and (later) district UI |
| `apps/api` | Node.js/Express, ESM, JavaScript | Auth, tenancy, CRUD, orchestration, persistence, audit, reports, SMS orchestration |
| `services/ml` | FastAPI, wrapping vendored `edutrace` | Feature building, inference, explanation, recourse, training, model versioning, the conversation/safeguarding *content* logic |
| Postgres | — | System of record |
| Redis | — | Job queue (BullMQ) + rate-limit counters + session/refresh-token denylist |

## Request flow: scoring a student

```
Teacher uploads CSV
        │
        ▼
apps/api  POST /api/v1/schools/:schoolId/uploads
        │  - validates file, stores raw upload, enqueues job (BullMQ)
        ▼
Background worker (apps/api/src/jobs)
        │  - parses CSV row by row
        │  - upserts Student + StudentObservation rows (operational_data)
        │  - checks ModelRegistration for an ACTIVE, APPROVED model
        │      no ACTIVE model  → job completes with "queued, awaiting model
        │                          approval" status; nothing is sent to ML
        │      ACTIVE model     → continues
        │  - strips PII, builds a pseudonymous student_key
        │      (StudentIdentity.pseudonym() equivalent, ported 1:1 from the
        │      Python StudentIdentity model so both sides derive the same key
        │      from the same per-tenant salt)
        │  - calls services/ml  POST /internal/v1/score/batch
        │      (service-to-service auth: HMAC-signed request, see below)
        ▼
services/ml  (vendored edutrace.serve.scorer / edutrace.serve.app logic)
        │  - validates against StudentObservation contract
        │  - refuses rows outside the domain guard (age, grade, term)
        │  - scores, computes SHAP drivers + recourse for top-K by capacity
        │  - returns RiskAssessment[] (no PII in the payload — student_key only)
        ▼
apps/api
        │  - persists RiskAssessment rows, linked back to the real Student by
        │    student_key (the PII↔pseudonym mapping lives only in apps/api's
        │    database, never in the ML service)
        │  - writes an audit log entry (score.batch)
        │  - populates the school's review queue
        ▼
Teacher dashboard reads the review queue from apps/api (never directly from
the ML service).
```

## Service-to-service authentication

The ML service is never exposed to the public internet (Section 6). In
Docker Compose it is only reachable on the internal network; `apps/api` is
the only client. Requests carry:

- `X-Service-Id: edutrace-api`
- `X-Service-Timestamp: <unix ms>`
- `X-Service-Signature: HMAC-SHA256(secret, serviceId + timestamp + rawBody)`

The ML service rejects requests older than 60 seconds (replay protection) or
with a bad signature. The shared secret is `ML_SERVICE_SHARED_SECRET`,
injected via environment variable / secret manager, never committed.

## Model governance enforcement (see also README)

```
apps/api                              services/ml
   │  GET /internal/v1/models/active ──►
   │  ◄────────────────────────────────  { version, card, provenance }
   │
   │  upsert into ModelRegistration
   │  (status defaults to DEVELOPMENT
   │   on first sight of a new version)
   │
   │  before any /predictions call:
   │    SELECT * FROM ModelRegistration
   │    WHERE version = <active> AND status = 'ACTIVE'
   │    none found → 409 "no approved production model"
```

Promotion `DEVELOPMENT → VALIDATION → APPROVED → ACTIVE` is a `SYSTEM_ADMIN`
action in Node (`PATCH /api/v1/admin/models/:version/status`), never automatic,
and every transition is audit-logged with the admin's id and a required
justification note.

## Multi-tenancy / school isolation

Every tenant-scoped table carries `schoolId`. Node's authorization middleware
attaches the authenticated user's `schoolId` from their verified session — it
is **never** taken from the request body or query string (Section 9). All
Prisma queries in tenant-scoped services are written through a small
`scopedTo(schoolId)` helper (Phase 3) so a missing `where: { schoolId }` clause
is a code-review-visible anomaly rather than a silent leak.

`SYSTEM_ADMIN` is the only role that can query across schools, and every
cross-school query is audit-logged separately from same-school queries.

## PII flow (Section 78)

```
Postgres (apps/api) → Node → strip PII → pseudonymous student_key
        → feature validation → services/ml → model → prediction + explanation
        → Node → Postgres (apps/api) → frontend
```

`StudentIdentity`-equivalent fields (name, guardian name, guardian MSISDN,
external id) live in a dedicated `StudentIdentity` table in Postgres with
tighter row-level access than `StudentObservation`. The ML service never
receives them. The Node layer that talks to the ML service builds request
payloads from a projection that excludes the `StudentIdentity` relation
entirely — enforced by the DTO/serializer in Phase 7, tested by a Phase 16
regression test asserting no PII field name ever appears in an outbound
ML-service request body.
