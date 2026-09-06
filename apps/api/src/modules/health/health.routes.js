import { Router } from "express";
import Redis from "ioredis";

import { env } from "../../config/env.js";
import { prisma } from "../../db/prisma.js";

export const healthRouter = Router();

// Liveness: process is up. Kept dependency-free on purpose so a database
// outage doesn't take down the load balancer's liveness check along with it.
healthRouter.get("/health/live", (req, res) => {
  res.json({ status: "ok" });
});

// Readiness: dependencies are reachable. Wired to real checks in Phase 3
// once the Prisma client and Redis connection are established at startup;
// for now it reports what's configured so `docker compose up` is debuggable.
healthRouter.get("/health/ready", async (_req, res) => {
  const checks = { database: "down", redis: "down", mlService: "down" };
  let redis;
  try {
    await prisma.$queryRaw`SELECT 1`;
    checks.database = "ok";
  } catch {
    // Keep readiness responses free of connection details.
  }
  try {
    redis = new Redis(env.REDIS_URL, {
      lazyConnect: true,
      maxRetriesPerRequest: 1,
    });
    await redis.connect();
    await redis.ping();
    checks.redis = "ok";
  } catch {
    // Keep readiness responses free of connection details.
  } finally {
    if (redis) redis.disconnect();
  }
  try {
    const response = await fetch(`${env.ML_SERVICE_URL}/health`, {
      signal: AbortSignal.timeout(2000),
    });
    if (response.ok) checks.mlService = "ok";
  } catch {
    // Keep readiness responses free of connection details.
  }
  const ready = Object.values(checks).every((value) => value === "ok");
  res
    .status(ready ? 200 : 503)
    .json({ status: ready ? "ok" : "degraded", checks });
});
