import { ZodError } from "zod";
import { logger } from "../utils/logger.js";

/**
 * Base class for errors that should be surfaced to the client with a
 * specific status code and a stable machine-readable code. Anything thrown
 * that is NOT an AppError is treated as a bug and returns a generic 500 —
 * we never leak internal error messages/stack traces to a client.
 */
export class AppError extends Error {
  constructor(
    message,
    { statusCode = 500, code = "INTERNAL_ERROR", details } = {},
  ) {
    super(message);
    this.statusCode = statusCode;
    this.code = code;
    this.details = details;
  }
}

export class NotFoundError extends AppError {
  constructor(message = "Resource not found") {
    super(message, { statusCode: 404, code: "NOT_FOUND" });
  }
}

export class ValidationError extends AppError {
  constructor(message = "Validation failed", details) {
    super(message, { statusCode: 422, code: "VALIDATION_ERROR", details });
  }
}

export class UnauthorizedError extends AppError {
  constructor(message = "Unauthorized") {
    super(message, { statusCode: 401, code: "UNAUTHORIZED" });
  }
}

export class ForbiddenError extends AppError {
  constructor(message = "Forbidden") {
    super(message, { statusCode: 403, code: "FORBIDDEN" });
  }
}

export class ConflictError extends AppError {
  constructor(message = "Conflict") {
    super(message, { statusCode: 409, code: "CONFLICT" });
  }
}

// 404 handler for unmatched routes — must be registered after all routes.
export function notFoundHandler(req, res, _next) {
  res.status(404).json({
    success: false,
    error: {
      code: "NOT_FOUND",
      message: `No route for ${req.method} ${req.originalUrl}`,
    },
    requestId: req.id,
  });
}

// Final error handler — must be registered last, after notFoundHandler.
export function errorHandler(err, req, res, _next) {
  if (err instanceof ZodError) {
    return res.status(422).json({
      success: false,
      error: {
        code: "VALIDATION_ERROR",
        message: "Request failed validation",
        details: err.issues,
      },
      requestId: req.id,
    });
  }

  if (err instanceof AppError) {
    if (err.statusCode >= 500) {
      logger.error({ err, requestId: req.id }, err.message);
    }
    return res.status(err.statusCode).json({
      success: false,
      error: { code: err.code, message: err.message, details: err.details },
      requestId: req.id,
    });
  }

  logger.error({ err, requestId: req.id }, "Unhandled error");
  return res.status(500).json({
    success: false,
    error: { code: "INTERNAL_ERROR", message: "An unexpected error occurred" },
    requestId: req.id,
  });
}
