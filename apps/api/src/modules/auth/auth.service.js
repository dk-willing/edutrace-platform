import crypto from "node:crypto";
import argon2 from "argon2";
import jwt from "jsonwebtoken";

import { env } from "../../config/env.js";
import {
  ConflictError,
  ForbiddenError,
  UnauthorizedError,
  ValidationError,
} from "../../middleware/errorHandler.js";

const refreshCookieName = "edutrace_refresh";

function hashToken(token) {
  return crypto.createHash("sha256").update(token).digest("hex");
}

function publicTeacher(teacher) {
  return {
    id: teacher.id,
    firstName: teacher.firstName,
    lastName: teacher.lastName,
    email: teacher.email,
    phone: teacher.phone,
    role: teacher.role,
    status: teacher.status,
    emailVerified: teacher.emailVerified,
    phoneVerified: teacher.phoneVerified,
    school: teacher.school
      ? {
          id: teacher.school.id,
          name: teacher.school.name,
          schoolCode: teacher.school.schoolCode,
        }
      : null,
  };
}

function signAccessToken(teacher) {
  return jwt.sign(
    { sub: teacher.id, role: teacher.role, schoolId: teacher.schoolId ?? null },
    env.JWT_ACCESS_SECRET,
    { expiresIn: env.JWT_ACCESS_TOKEN_TTL },
  );
}

function assertCanLogin(teacher) {
  if (teacher.status === "SUSPENDED" || teacher.status === "DEACTIVATED") {
    throw new ForbiddenError(
      "This account is not active. Contact your school administrator.",
    );
  }
  if (!teacher.emailVerified) {
    throw new ForbiddenError("Verify your email before signing in.");
  }
  if (teacher.status === "PENDING_SCHOOL_APPROVAL") {
    throw new ForbiddenError("Your account is waiting for school approval.");
  }
  if (teacher.status !== "ACTIVE") {
    throw new ForbiddenError("This account is not ready to sign in.");
  }
}

export function getRefreshCookieName() {
  return refreshCookieName;
}

export async function registerTeacher(prisma, input) {
  const email = input.email.trim().toLowerCase();
  const school = await prisma.school.findUnique({
    where: { schoolCode: input.schoolCode.trim() },
  });
  if (
    !school ||
    school.status === "SUSPENDED" ||
    school.status === "ARCHIVED"
  ) {
    throw new ValidationError(
      `School code "${input.schoolCode.trim().toUpperCase()}" was not found or is not available. Ask your school administrator to onboard the school first.`,
    );
  }

  const existing = await prisma.teacher.findUnique({ where: { email } });
  if (existing)
    throw new ConflictError("An account with that email already exists.");

  const passwordHash = await argon2.hash(input.password);
  const rawVerificationToken = crypto.randomBytes(32).toString("hex");
  const teacher = await prisma.teacher.create({
    data: {
      schoolId: school.id,
      firstName: input.firstName.trim(),
      lastName: input.lastName.trim(),
      email,
      phone: input.phone?.trim() || null,
      passwordHash,
      status: "PENDING_EMAIL_VERIFICATION",
      emailVerifications: {
        create: {
          tokenHash: hashToken(rawVerificationToken),
          expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000),
        },
      },
    },
    include: { school: true },
  });

  return {
    teacher: publicTeacher(teacher),
    verificationToken: rawVerificationToken,
  };
}

export async function verifyEmail(prisma, token) {
  const record = await prisma.emailVerificationToken.findUnique({
    where: { tokenHash: hashToken(token) },
    include: { teacher: { include: { school: true } } },
  });
  if (!record || record.usedAt || record.expiresAt <= new Date()) {
    throw new ValidationError(
      "This email verification link is invalid or expired.",
    );
  }

  const teacher = await prisma.$transaction(async (tx) => {
    await tx.emailVerificationToken.update({
      where: { id: record.id },
      data: { usedAt: new Date() },
    });
    return tx.teacher.update({
      where: { id: record.teacherId },
      data: { emailVerified: true, status: "PENDING_SCHOOL_APPROVAL" },
      include: { school: true },
    });
  });
  return publicTeacher(teacher);
}

export async function login(prisma, input) {
  const email = input.email.trim().toLowerCase();
  const teacher = await prisma.teacher.findUnique({
    where: { email },
    include: { school: true },
  });
  if (!teacher) throw new UnauthorizedError("Invalid email or password.");
  if (teacher.lockedUntil && teacher.lockedUntil > new Date()) {
    throw new UnauthorizedError("Too many failed attempts. Try again later.");
  }

  const valid = await argon2.verify(teacher.passwordHash, input.password);
  if (!valid) {
    const failedLoginCount = teacher.failedLoginCount + 1;
    const lockedUntil =
      failedLoginCount >= env.LOGIN_MAX_ATTEMPTS
        ? new Date(Date.now() + env.LOGIN_LOCKOUT_MINUTES * 60 * 1000)
        : null;
    await prisma.teacher.update({
      where: { id: teacher.id },
      data: { failedLoginCount, lockedUntil },
    });
    throw new UnauthorizedError("Invalid email or password.");
  }

  assertCanLogin(teacher);
  const rawRefreshToken = crypto.randomBytes(48).toString("base64url");
  const expiresAt = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000);
  await prisma.$transaction([
    prisma.teacher.update({
      where: { id: teacher.id },
      data: { failedLoginCount: 0, lockedUntil: null, lastLoginAt: new Date() },
    }),
    prisma.refreshToken.create({
      data: {
        teacherId: teacher.id,
        tokenHash: hashToken(rawRefreshToken),
        expiresAt,
      },
    }),
  ]);

  return {
    accessToken: signAccessToken(teacher),
    refreshToken: rawRefreshToken,
    teacher: publicTeacher(teacher),
  };
}

export async function refreshSession(prisma, rawRefreshToken) {
  if (!rawRefreshToken)
    throw new UnauthorizedError("Refresh session is missing.");
  const record = await prisma.refreshToken.findUnique({
    where: { tokenHash: hashToken(rawRefreshToken) },
    include: { teacher: { include: { school: true } } },
  });
  if (!record || record.revokedAt || record.expiresAt <= new Date()) {
    throw new UnauthorizedError("Refresh session is invalid or expired.");
  }
  assertCanLogin(record.teacher);

  const nextToken = crypto.randomBytes(48).toString("base64url");
  const nextExpiresAt = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000);
  await prisma.$transaction(async (tx) => {
    await tx.refreshToken.update({
      where: { id: record.id },
      data: { revokedAt: new Date(), replacedByTokenId: "pending" },
    });
    const replacement = await tx.refreshToken.create({
      data: {
        teacherId: record.teacherId,
        tokenHash: hashToken(nextToken),
        expiresAt: nextExpiresAt,
      },
    });
    await tx.refreshToken.update({
      where: { id: record.id },
      data: { replacedByTokenId: replacement.id },
    });
  });
  return {
    accessToken: signAccessToken(record.teacher),
    refreshToken: nextToken,
    teacher: publicTeacher(record.teacher),
  };
}

export async function revokeRefreshToken(prisma, rawRefreshToken) {
  if (!rawRefreshToken) return;
  await prisma.refreshToken.updateMany({
    where: { tokenHash: hashToken(rawRefreshToken), revokedAt: null },
    data: { revokedAt: new Date() },
  });
}

export { publicTeacher };
