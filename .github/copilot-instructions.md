# EduTrace repository instructions

## Repository layout

- `apps/api`: Node.js/Express backend using JavaScript ESM, not TypeScript.
- `apps/web`: Next.js teacher/admin frontend.
- `packages/db`: Prisma schema and migrations; the shared database source of truth.
- `services/ml`: FastAPI wrapper around the vendored `edutrace` package.

## Development rules

- Preserve the existing workspace structure and package conventions.
- Keep changes focused and type-safe where types are available.
- Do not modify `services/ml/vendor_edutrace` or its supplied model artifacts; extend behavior through `services/ml/app`.
- Durable ML responses belong in Postgres through the Node API; the ML service's in-memory store is not the system of record.
- Never bypass model governance or pre-approve supplied models. Real scoring requires an `ACTIVE` model registration; use the clearly labelled demo endpoint for fixtures only.
- Preserve safety-critical behavior such as banned-phrase filtering, review gates, safeguarding referrals, and model limitations.
- Do not commit secrets or edit generated environment files as a substitute for configuration.

## Useful commands

- `npm run dev:api`: start the API.
- `npm run dev:web`: start the web app.
- `npm run dev:ml`: start the ML service.
- `npm run check`: validate the database, lint the API, run API tests, and build the web app.
- `npm run db:generate`: generate Prisma client artifacts.
- `npm run db:migrate`: run development migrations.

When changing database schema, update the Prisma schema and migration workflow together. When changing API behavior, add or update the nearest existing API tests.
