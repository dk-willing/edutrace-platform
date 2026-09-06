# Production Deployment

This document describes the supported production topology. Do not expose the
ML service publicly.

## Services

Deploy five private/public components:

- Managed PostgreSQL
- Managed Redis
- `ml-service` from `services/ml/Dockerfile`, private only
- `api` from the repository root with `apps/api/Dockerfile`
- `web` from `apps/web/Dockerfile`, public HTTPS domain

Railway, Render, and AWS ECS/Fargate can all host this topology. Railway is the
lowest-operations option for an initial team environment; AWS is preferable
when compliance, networking, backups, and traffic controls require deeper
customization.

## Build and start settings

API build context must be the repository root:

```text
Dockerfile: apps/api/Dockerfile
Build context: .
Start command: npm start
```

The API start command runs `prisma migrate deploy` before starting Express.
Migrations must be reviewed and committed before deployment.

Web:

```text
Dockerfile: apps/web/Dockerfile
Build context: apps/web
Start command: npm run start
Port: 3000
```

ML:

```text
Dockerfile: services/ml/Dockerfile
Start command: image default command
Port: 8000 private
```

## Required secrets

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
EDUTRACE_SMS_PROVIDER=arkesel
ARKESEL_API_KEY=...
EDUTRACE_SMS_SENDER_ID=...
```

The API refuses production startup without SMTP credentials. The ML service
must receive the same shared secret and API key as the API. The Arkesel sender
ID must be approved before real messages are enabled.

## Release sequence

1. Build and scan the API, web, and ML images.
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
