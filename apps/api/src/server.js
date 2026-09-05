import { createApp } from './app.js';
import { env } from './config/env.js';
import { logger } from './utils/logger.js';

const app = createApp();

const server = app.listen(env.PORT, () => {
  logger.info(`edutrace-api listening on :${env.PORT} (${env.NODE_ENV})`);
});

// Graceful shutdown: stop accepting new connections, let in-flight requests
// (including anything mid-flight to the ML service) finish, then exit. Matters
// in Kubernetes/ECS where SIGTERM precedes a hard kill by a fixed grace period.
function shutdown(signal) {
  logger.info(`received ${signal}, shutting down`);
  server.close((err) => {
    if (err) {
      logger.error({ err }, 'error during shutdown');
      process.exit(1);
    }
    process.exit(0);
  });
  // Belt and braces: if close() hangs (e.g. a leaked keep-alive connection),
  // don't let the process hang forever behind an orchestrator's SIGKILL timer.
  setTimeout(() => process.exit(1), 10_000).unref();
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));

process.on('unhandledRejection', (reason) => {
  logger.error({ err: reason }, 'unhandled promise rejection');
});
