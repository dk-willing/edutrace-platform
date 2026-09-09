import dotenv from "dotenv";
import { fileURLToPath } from "node:url";
import { z } from "zod";

dotenv.config({
  path: fileURLToPath(new URL("../../../../.env", import.meta.url)),
});

// Fail fast and loud on missing/malformed config, rather than discovering a
// missing secret the first time a request needs it in production.
const EnvSchema = z
  .object({
    NODE_ENV: z
      .enum(["development", "test", "production"])
      .default("development"),
    PORT: z.coerce.number().int().positive().default(5000),
    FRONTEND_URL: z.string().url().default("http://localhost:3000"),

    DATABASE_URL: z.string().min(1, "DATABASE_URL is required"),
    REDIS_URL: z.string().min(1, "REDIS_URL is required"),

    ML_SERVICE_URL: z.string().url(),
    ML_SERVICE_SHARED_SECRET: z
      .string()
      .min(16, "ML_SERVICE_SHARED_SECRET must be at least 16 chars"),
    ML_SERVICE_API_KEY: z
      .string()
      .default(process.env.EDUTRACE_API_KEY || "dev_demo_key_change_me"),
    EDUTRACE_SMS_PROVIDER: z.enum(["console", "arkesel"]).default("console"),
    ARKESEL_API_KEY: z.string().optional(),

    JWT_ACCESS_SECRET: z.string().min(16),
    JWT_REFRESH_SECRET: z.string().min(16),
    JWT_ACCESS_TOKEN_TTL: z.string().default("15m"),
    JWT_REFRESH_TOKEN_TTL: z.string().default("30d"),

    PII_PSEUDONYM_SALT: z.string().min(8),

    SMTP_HOST: z.string().optional(),
    SMTP_PORT: z.coerce.number().int().optional(),
    SMTP_USER: z.string().optional(),
    SMTP_PASSWORD: z.string().optional(),
    EMAIL_FROM_ADDRESS: z.string().email().default("no-reply@edutrace.example"),
    RESEND_API_KEY: z.string().optional(),

    LOGIN_MAX_ATTEMPTS: z.coerce.number().int().positive().default(5),
    LOGIN_LOCKOUT_MINUTES: z.coerce.number().int().positive().default(15),
  })
  .superRefine((value, context) => {
    if (value.NODE_ENV === "production") {
      if (!value.RESEND_API_KEY) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["RESEND_API_KEY"],
          message: "Required in production.",
        });
      }
      if (value.EDUTRACE_SMS_PROVIDER === "arkesel" && !value.ARKESEL_API_KEY) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["ARKESEL_API_KEY"],
          message: "Required when Arkesel is enabled.",
        });
      }
    }
  });

function loadEnv() {
  const parsed = EnvSchema.safeParse(process.env);
  if (!parsed.success) {
    // Printed, not thrown-as-is, so the missing/invalid keys are legible in
    // container logs rather than buried in a Zod stack trace.
    const issues = parsed.error.issues
      .map((i) => `  - ${i.path.join(".")}: ${i.message}`)
      .join("\n");
    console.error(`Invalid environment configuration:\n${issues}`);
    process.exit(1);
  }
  return parsed.data;
}

export const env = loadEnv();
