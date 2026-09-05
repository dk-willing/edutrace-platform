import { Router } from "express";
import { z } from "zod";

import { prisma } from "../../db/prisma.js";
import {
  getRefreshCookieName,
  login,
  refreshSession,
  registerTeacher,
  revokeRefreshToken,
  verifyEmail,
} from "./auth.service.js";
import { requireAuth } from "./auth.middleware.js";
import { asyncHandler } from "../../utils/asyncHandler.js";
import { env } from "../../config/env.js";
import { logger } from "../../utils/logger.js";

const router = Router();
const credentials = z.object({
  email: z.string().email(),
  password: z.string().min(12).max(128),
});
const registerSchema = credentials.extend({
  firstName: z.string().trim().min(1).max(80),
  lastName: z.string().trim().min(1).max(80),
  phone: z.string().trim().max(32).optional(),
  schoolCode: z.string().trim().min(2).max(40),
});
const cookieOptions = {
  httpOnly: true,
  sameSite: "lax",
  secure: process.env.NODE_ENV === "production",
  path: "/api/v1/auth",
};

function setRefreshCookie(res, token) {
  res.cookie(getRefreshCookieName(), token, cookieOptions);
}

router.post(
  "/register",
  asyncHandler(async (req, res) => {
    const result = await registerTeacher(
      prisma,
      registerSchema.parse(req.body),
    );
    if (env.NODE_ENV !== "production") {
      const verificationUrl = `${env.FRONTEND_URL}/verify-email?token=${encodeURIComponent(result.verificationToken)}`;
      // Development-only convenience. Never expose verification tokens in API responses or production logs.
      // eslint-disable-next-line no-console
      console.log(
        `\n[EduTrace] Verification link for ${result.teacher.email}:\n${verificationUrl}\n`,
      );
    }
    logger.info({ email: result.teacher.email }, "teacher account created");
    res.status(201).json({
      success: true,
      teacher: result.teacher,
    });
  }),
);

router.post(
  "/verify-email",
  asyncHandler(async (req, res) => {
    const input = z.object({ token: z.string().min(32) }).parse(req.body);
    res.json({
      success: true,
      teacher: await verifyEmail(prisma, input.token),
    });
  }),
);

router.post(
  "/login",
  asyncHandler(async (req, res) => {
    const result = await login(prisma, credentials.parse(req.body));
    logger.info(
      { email: result.teacher.email, role: result.teacher.role },
      "user login successful",
    );
    setRefreshCookie(res, result.refreshToken);
    res.json({
      success: true,
      accessToken: result.accessToken,
      teacher: result.teacher,
    });
  }),
);

router.post(
  "/refresh",
  asyncHandler(async (req, res) => {
    const result = await refreshSession(
      prisma,
      req.cookies[getRefreshCookieName()],
    );
    setRefreshCookie(res, result.refreshToken);
    res.json({
      success: true,
      accessToken: result.accessToken,
      teacher: result.teacher,
    });
  }),
);

router.post(
  "/logout",
  requireAuth,
  asyncHandler(async (req, res) => {
    await revokeRefreshToken(prisma, req.cookies[getRefreshCookieName()]);
    res.clearCookie(getRefreshCookieName(), cookieOptions);
    res.status(204).send();
  }),
);

router.get("/me", requireAuth, (req, res) => {
  res.json({ success: true, teacher: req.auth.teacher });
});

export { router as authRouter };
