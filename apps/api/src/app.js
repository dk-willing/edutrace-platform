import express from "express";
import helmet from "helmet";
import cors from "cors";
import cookieParser from "cookie-parser";
import rateLimit from "express-rate-limit";
import morgan from "morgan";

import { env } from "./config/env.js";
import { requestId } from "./middleware/requestId.js";
import { errorHandler, notFoundHandler } from "./middleware/errorHandler.js";
import { healthRouter } from "./modules/health/health.routes.js";
import { authRouter } from "./modules/auth/auth.routes.js";
import { adminRouter } from "./modules/admin/admin.routes.js";
import { classesRouter } from "./modules/classes/classes.routes.js";
import { studentsRouter } from "./modules/students/students.routes.js";
import { dashboardRouter } from "./modules/dashboard/dashboard.routes.js";
import { importsRouter } from "./modules/imports/imports.routes.js";
import { reportsRouter } from "./modules/reports/reports.routes.js";

export function createApp() {
  const app = express();

  // Trust the first proxy hop (load balancer/reverse proxy) so req.ip and
  // rate limiting see the real client address, not the proxy's.
  app.set("trust proxy", 1);

  app.use(requestId);
  morgan.token("request-id", (req) => req.id || "-");
  app.use(
    morgan(
      env.NODE_ENV === "production"
        ? ":remote-addr :method :url :status :response-time ms request=:request-id"
        : ":method :url :status :response-time ms request=:request-id",
      {
        skip: (req) => req.url === "/health/live",
      },
    ),
  );

  app.use(helmet());
  app.use(
    cors({
      origin:
        env.NODE_ENV === "production"
          ? [] /* filled in Phase 15 with real origins */
          : true,
      credentials: true,
    }),
  );
  app.use(cookieParser());
  app.use(express.json({ limit: "2mb" }));
  app.use(express.urlencoded({ extended: true }));

  // Global baseline rate limit. Auth and CSV-upload routes get tighter,
  // route-specific limits layered on top in Phase 3 / Phase 6.
  app.use(
    rateLimit({
      windowMs: 15 * 60 * 1000,
      max: env.NODE_ENV === "production" ? 300 : 10000,
      standardHeaders: true,
      legacyHeaders: false,
    }),
  );

  app.use(healthRouter);
  app.use("/api/v1/auth", authRouter);
  app.use("/api/v1/admin", adminRouter);
  app.use("/api/v1/classes", classesRouter);
  app.use("/api/v1/students", studentsRouter);
  app.use("/api/v1/dashboard", dashboardRouter);
  app.use("/api/v1/imports", importsRouter);
  app.use("/api/v1/reports", reportsRouter);

  // Feature routers are mounted here as each phase lands:
  //   app.use('/api/v1/auth', authRouter);            // Phase 3
  //   app.use('/api/v1/schools', schoolsRouter);       // Phase 4
  //   app.use('/api/v1/classes', classesRouter);       // Phase 5
  //   app.use('/api/v1/uploads', uploadsRouter);       // Phase 6
  //   app.use('/api/v1/predictions', predictionsRouter); // Phase 7/8
  //   app.use('/api/v1/questionnaires', questionnairesRouter); // Phase 9
  //   app.use('/api/v1/safeguarding', safeguardingRouter); // Phase 10
  //   app.use('/api/v1/interventions', interventionsRouter); // Phase 11
  //   app.use('/api/v1/reports', reportsRouter);       // Phase 13
  //   app.use('/api/v1/admin', adminRouter);           // Phase 14
  //   app.use('/api/docs', swaggerRouter);             // Phase 18

  app.use(notFoundHandler);
  app.use(errorHandler);

  return app;
}
