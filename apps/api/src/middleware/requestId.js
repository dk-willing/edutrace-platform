import { randomUUID } from 'node:crypto';

// Attaches a request id early so every log line and error response can be
// correlated back to a single request, including across the service-to-service
// hop into the ML service (forwarded as X-Request-Id).
export function requestId(req, res, next) {
  req.id = req.headers['x-request-id'] || randomUUID();
  res.setHeader('X-Request-Id', req.id);
  next();
}
