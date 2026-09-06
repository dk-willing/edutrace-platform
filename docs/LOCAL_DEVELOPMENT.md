# Local development

## Docker path

From the repository root:

```powershell
docker compose up --build
```

The services are then available at:

- Web: `http://localhost:3000`
- Node API: `http://localhost:4000`
- API liveness: `http://localhost:4000/health/live`
- ML service: internal to Docker only

In another terminal, apply the Prisma schema to the development database:

```powershell
docker compose exec api npx prisma db push --schema=./prisma/schema.prisma
```

Bootstrap a school and system administrator:

```powershell
docker compose exec api node src/scripts/create-school.js --name="ABC Junior High" --code=ABC-JHS --district=Accra --region=Greater-Accra --admin-email=admin@example.com --admin-password="change-this-password"
```

The command prints the school code. Teachers use that code on `/register`.
The bootstrap admin can sign in at `/login`; system administrators are sent to
the `/admin` page, where they can create additional schools and assign codes
through the UI.

## Local process path

Use Node 20+, Python 3.12+, PostgreSQL, and Redis. Copy `.env.example` to
`.env`, fill the required values, and install dependencies separately if the
root workspace install is unavailable:

```powershell
Push-Location apps/web; npm install --workspaces=false; Pop-Location
npm install
npm install --workspace=@edutrace/api dotenv
npm run api:generate
npm run db:migrate
```

For Supabase, use the transaction pooler on `DATABASE_URL` and the session
pooler on `DIRECT_URL`. Both URLs must include `sslmode=require`:

```env
DATABASE_URL="postgresql://...:...@aws-1-REGION.pooler.supabase.com:6543/postgres?pgbouncer=true&sslmode=require"
DIRECT_URL="postgresql://...:...@aws-1-REGION.pooler.supabase.com:5432/postgres?sslmode=require"
```

This repository does not contain a migration yet. After the database URL is
reachable, create and apply the initial migration once:

```powershell
npm run migrate:dev --workspace=@edutrace/db -- --name init
```

Use the direct/session URL for that command. `prisma migrate dev` will create
`packages/db/prisma/migrations/` and apply the schema. For a disposable local
database, `prisma db push` is also acceptable, but it does not create migration
history.

Start the ML service from `services/ml` with its Python environment:

```powershell
Push-Location services/ml
py -3.12 -m venv .venv
& .\.venv\Scripts\Activate.ps1
pip install -e .\vendor
$env:ML_SERVICE_SHARED_SECRET = "replace-with-the-same-secret-as-.env"
$env:EDUTRACE_API_KEY = "dev_demo_key_change_me"
uvicorn app.main:app --host 127.0.0.1 --port 8000
Pop-Location
```

Then use separate terminals for:

```powershell
npm run dev:api
Push-Location apps/web; npm run dev; Pop-Location
```

For the separate-process API, make sure `.env` contains `PORT=5000` or uses
the default, plus a reachable `DATABASE_URL`, `REDIS_URL`,
`ML_SERVICE_URL=http://localhost:8000`, and the same `ML_SERVICE_SHARED_SECRET`
used by the ML terminal. Set `ML_SERVICE_API_KEY` to the same value as
`EDUTRACE_API_KEY` when using a non-default ML API key.

The standalone web client defaults to `http://localhost:5000`, matching the
local API default. Docker overrides this with `NEXT_PUBLIC_API_URL` and uses
port `4000` for the Compose API.

If using an already-running Postgres database, set `DATABASE_URL` to that
database before running the Prisma commands. The API will refuse to start when
required environment variables are missing.

## Important safety notes

The supplied ML artifacts are development/demo models and are not approved for
real learners. Production scoring must remain unavailable until an approved
model is registered. Also rotate any real credentials that have ever been put
in a local `.env` or shared in a terminal/chat.
