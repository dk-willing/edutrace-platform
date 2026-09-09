# Production Deployment

This document describes the supported production topology. Do not expose the
ML service publicly.

## Services

Deploy five private/public components as managed services or native processes:

- Managed PostgreSQL
- Managed Redis
- `ml-service` from `services/ml`, private only
- `api` from `apps/api`, public API domain
- `web` from `apps/web`, public HTTPS domain

Railway, Render, and AWS ECS/Fargate can all host this topology. Railway is the
lowest-operations option for an initial team environment; AWS is preferable
when compliance, networking, backups, and traffic controls require deeper
customization.

## Build and start settings

API:

```text
Working directory: apps/api
Build: npm ci && npm run db:generate
Start: npm start
```

The API start command runs `prisma migrate deploy` before starting Express.
Migrations must be reviewed and committed before deployment.

Web:

```text
Working directory: apps/web
Build: npm ci && npm run build
Start: npm run start
Port: 3000
```

ML:

```text
Working directory: services/ml
Install: pip install -e ./vendor
Start: uvicorn app.main:app --host 0.0.0.0 --port 8000
Port: 8000 private
```

## Required secrets

For the current deployment URLs, configure these platform variables:

Vercel web service:

```env
NEXT_PUBLIC_API_URL=https://edutrace-platform-1.onrender.com
```

Render API service:

```env
FRONTEND_URL=https://edutrace-platform-web.vercel.app
PORT=10000
NODE_ENV=production
```

`NEXT_PUBLIC_API_URL` is embedded during the Vercel build, so save the
variable and redeploy the web service after changing it. `FRONTEND_URL` must
match the Vercel origin exactly so API CORS permits browser requests.

Set these in the platform secret manager. Never use the Compose development
fallbacks in a shared environment:

```env
NODE_ENV=production
FRONTEND_URL=https://app.example.com
DATABASE_URL=...
DIRECT_URL=...
REDIS_URL=...
ML_SERVICE_URL=http://ml-service:8000
ML_SERVICE_SHARED_SECRET=...
ML_SERVICE_API_KEY=...
EDUTRACE_API_KEY=...
JWT_ACCESS_SECRET=...
JWT_REFRESH_SECRET=...
PII_PSEUDONYM_SALT=...
SMTP_HOST=...
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
EMAIL_FROM_ADDRESS=no-reply@example.com
EDUTRACE_SMS_PROVIDER=console
ARKESEL_API_KEY=
EDUTRACE_SMS_SENDER_ID=EDUTRACE
```

The API refuses production startup without SMTP credentials. The ML service
must receive the same shared secret and API key as the API. Keep SMS on
`console` for the first launch unless Arkesel has been separately verified;
switch to `arkesel` only after adding the API key and approved sender ID.

Generate fresh application secrets locally with:

```powershell
npm run secrets:generate
```

This creates the ignored `.env.production.generated` file. Copy its values
into your platform secret manager, then fill in the managed database, Redis,
frontend domain, and transactional email provider values.

## Release sequence

1. Build and scan the API, web, and ML dependencies.
2. Apply committed migrations with the API release command.
3. Start the private ML service and verify `GET /health` reports a loaded model.
4. Start the API and verify `/health/live` and `/health/ready`.
5. Start the web service with `NEXT_PUBLIC_API_URL` pointing to the API HTTPS URL.
6. Run smoke tests for login, registration email, password reset email, CSV preview,
   report download, and tenant isolation.
7. Confirm database backups, retention, alerting, and rollback procedure.

## Model gate

The bundled model is marked development/demo and must not be approved for real
learners. Register and approve a validated production model through the model
governance process before enabling real scoring.
