# Phase plan

Tracking against the 18 phases in the master spec. Each phase ends with tests
passing before moving on.

| Phase | Scope                                             | Status                                  |
| ----- | ------------------------------------------------- | --------------------------------------- |
| 1     | Architecture and repository setup                 | **Done (this commit)**                  |
| 2     | Database schema and migrations                    | **Done (this commit)**                  |
| 3     | Authentication and authorization                  | **In progress (core flow implemented)** |
| 4     | School and teacher onboarding                     | **Core flow implemented**               |
| 5     | Class and student management                      | **Core API implemented**                |
| 6     | CSV ingestion                                     | Pending                                 |
| 7     | Python AI service integration (Node ↔ ML service) | Pending                                 |
| 8     | Predictions and explainability                    | Pending                                 |
| 9     | Questionnaire/support system                      | Pending                                 |
| 10    | Safeguarding                                      | Pending                                 |
| 11    | Interventions and follow-ups                      | Pending                                 |
| 12    | Arkesel SMS                                       | Pending                                 |
| 13    | Dashboards and reporting                          | Pending                                 |
| 14    | Admin portal                                      | **School-management UI implemented**    |
| 15    | Security hardening                                | Pending                                 |
| 16    | Testing                                           | Pending                                 |
| 17    | Docker/deployment                                 | Pending                                 |
| 18    | Documentation and final QA                        | Pending                                 |

## Phase 1 deliverables (this commit)

- Monorepo layout: `apps/api`, `apps/web` (stub), `services/ml`, `packages/db`.
- Vendored, unmodified copy of the supplied `edutrace-v0.2.0` package and its
  two model artifacts under `services/ml/vendor_edutrace*`.
- `docker-compose.yml` wiring Postgres, Redis, the Node API, and the ML
  service for local development (frontend added when Phase 4+ needs it).
- `docs/ARCHITECTURE.md`: data flow, service boundaries, model governance.

## Phase 2 deliverables (this commit)

- `packages/db/prisma/schema.prisma`: full relational schema covering
  schools, teachers/roles, classes, students, student identity (PII,
  isolated), student observations (operational data), the model registry,
  risk assessments, review outcomes, needs profiles, safeguarding escalations
  (metadata-only, mirroring the Python `EscalationRecord` shape), audit log,
  notification log, CSV upload jobs, and auth tables (refresh tokens, email
  verification, password reset).
- Indexes on every `schoolId` foreign key for tenant-scoped query performance,
  per Section 76.
- `operational_data` vs `training_dataset` kept as genuinely separate tables
  (`StudentObservation` vs `TrainingDatasetRecord`) per Section 79 — nothing
  promotes a row from one to the other automatically; that will be an
  explicit, audited admin action implemented in Phase 7/8.

## What is deliberately NOT built yet

- No actual migration has been run against a live Postgres instance — there
  isn't one in this sandbox. `schema.prisma` is written to be run with
  `npx prisma migrate dev` against a real database in Phase 3, and the
  Docker Compose file provisions that database.
- No frontend pages yet — `apps/web` is a placeholder until Phase 4 needs a
  login screen.
- No real trained model. Both supplied models remain registered as
  `DEVELOPMENT` and unapproved, per `STATUS.md`.

## Phase 3 work delivered so far

- School-bound teacher registration by an existing school code; unavailable
  schools are rejected server-side.
- Argon2 password hashing, email-verification tokens, account lockout after
  repeated failed logins, JWT access tokens, rotating refresh tokens in an
  HttpOnly cookie, logout, and current-user lookup.
- Authentication middleware reloads the teacher from Postgres on every request,
  checks account status, and attaches the authenticated school identity.
- `SYSTEM_ADMIN` teachers may have no school so they can create the first
  school; ordinary teacher accounts remain linked to their selected school.

The remaining Phase 3/4 work is the admin bootstrap, school management,
teacher approval endpoint, email delivery adapter, and integration tests against
Postgres.

The admin API now includes school creation/listing, teacher listing, and
school-scoped teacher approval. Prisma generation is also reproducible through
`npm run api:generate` for standalone local installs.

Phase 5 now includes school-scoped class creation/listing, teacher ownership
checks, student creation, class student listing, duplicate external-ID checks,
and audit events for class/student creation.

The admin portal now includes a real `/admin` school-management page backed by
the protected admin API. System administrators can create schools, assign
unique registration codes, and view existing schools.
