import { Router } from 'express';

export const healthRouter = Router();

// Liveness: process is up. Kept dependency-free on purpose so a database
// outage doesn't take down the load balancer's liveness check along with it.
healthRouter.get('/health/live', (req, res) => {
  res.json({ status: 'ok' });
});

// Readiness: dependencies are reachable. Wired to real checks in Phase 3
// once the Prisma client and Redis connection are established at startup;
// for now it reports what's configured so `docker compose up` is debuggable.
healthRouter.get('/health/ready', async (req, res) => {
  const checks = {
    database: 'unknown',
    redis: 'unknown',
    mlService: 'unknown',
  };
  res.json({ status: 'ok', checks });
});
