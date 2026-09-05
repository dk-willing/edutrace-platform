import pino from "pino";
import { env } from "../config/env.js";

// Structured JSON logging in every environment, human-readable pretty-print
// only in development. Never log request/response bodies wholesale here —
// individual routes redact PII fields explicitly before logging anything
// beyond ids and status codes (see docs/ARCHITECTURE.md, PII flow).
export const logger = pino({
  level: env.NODE_ENV === "production" ? "info" : "debug",
  redact: {
    paths: [
      "req.headers.authorization",
      "req.headers.cookie",
      "*.password",
      "*.passwordHash",
      "*.guardianMsisdn",
      "*.studentName",
      "*.guardianName",
    ],
    censor: "[REDACTED]",
  },
});
