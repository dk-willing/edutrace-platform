import { Router } from "express";
import { z } from "zod";

import { prisma } from "../../db/prisma.js";
import {
  ConflictError,
  ForbiddenError,
  NotFoundError,
} from "../../middleware/errorHandler.js";
import { requireAuth, requireRole } from "../auth/auth.middleware.js";
import { asyncHandler } from "../../utils/asyncHandler.js";

const router = Router();
const schoolSchema = z.object({
  name: z.string().trim().min(2).max(160),
  schoolCode: z
    .string()
    .trim()
    .min(2)
    .max(40)
    .regex(/^[A-Za-z0-9-]+$/),
  district: z.string().trim().min(2).max(100),
  region: z.string().trim().min(2).max(100),
  address: z.string().trim().max(300).optional(),
  contactEmail: z.string().email().optional(),
  contactPhone: z.string().trim().max(32).optional(),
});

router.use(requireAuth);

async function getAdminSchoolIds(req) {
  if (req.auth.role === "SCHOOL_ADMIN")
    return [req.auth.schoolId].filter(Boolean);
  const schools = await prisma.school.findMany({
    where: { onboardedByAdminId: req.auth.teacherId },
    select: { id: true },
  });
  return schools.map((school) => school.id);
}

router.post(
  "/schools",
  requireRole("SYSTEM_ADMIN"),
  asyncHandler(async (req, res) => {
    const input = schoolSchema.parse(req.body);
    const schoolCode = input.schoolCode.toUpperCase();
    const existing = await prisma.school.findUnique({ where: { schoolCode } });
    if (existing)
      throw new ConflictError("That school code is already in use.");

    const school = await prisma.$transaction(async (tx) => {
      const created = await tx.school.create({
        data: {
          ...input,
          schoolCode,
          address: input.address || null,
          contactEmail: input.contactEmail || null,
          contactPhone: input.contactPhone || null,
          status: "ACTIVE",
          onboardedByAdminId: req.auth.teacherId,
        },
      });
      await tx.auditLog.create({
        data: {
          schoolId: created.id,
          actorId: req.auth.teacherId,
          event: "SCHOOL_CREATED",
          payload: { schoolCode, source: "admin_api" },
        },
      });
      return created;
    });
    res.status(201).json({ success: true, school });
  }),
);

router.get(
  "/schools",
  requireRole("SYSTEM_ADMIN"),
  asyncHandler(async (req, res) => {
    const schools = await prisma.school.findMany({
      where: { onboardedByAdminId: req.auth.teacherId },
      orderBy: { createdAt: "desc" },
      select: {
        id: true,
        name: true,
        schoolCode: true,
        district: true,
        region: true,
        status: true,
        createdAt: true,
      },
    });
    res.json({ success: true, schools });
  }),
);

router.post(
  "/teachers/:teacherId/approve",
  requireRole("SYSTEM_ADMIN", "SCHOOL_ADMIN"),
  asyncHandler(async (req, res) => {
    const teacher = await prisma.teacher.findUnique({
      where: { id: req.params.teacherId },
    });
    if (!teacher) throw new NotFoundError("Teacher not found.");
    const schoolIds = await getAdminSchoolIds(req);
    if (!teacher.schoolId || !schoolIds.includes(teacher.schoolId)) {
      throw new ForbiddenError(
        "You cannot approve a teacher outside your school administration scope.",
      );
    }
    const updated = await prisma.teacher.update({
      where: { id: teacher.id },
      data: {
        status: "ACTIVE",
        approvedByAdminId: req.auth.teacherId,
        approvedAt: new Date(),
      },
      include: { school: true },
    });
    await prisma.auditLog.create({
      data: {
        schoolId: updated.schoolId,
        actorId: req.auth.teacherId,
        event: "TEACHER_APPROVED",
        payload: { teacherId: updated.id },
      },
    });
    res.json({
      success: true,
      teacher: {
        id: updated.id,
        email: updated.email,
        status: updated.status,
        school: updated.school
          ? {
              id: updated.school.id,
              name: updated.school.name,
              schoolCode: updated.school.schoolCode,
            }
          : null,
      },
    });
  }),
);

router.get(
  "/teachers",
  requireRole("SYSTEM_ADMIN", "SCHOOL_ADMIN"),
  asyncHandler(async (req, res) => {
    const schoolIds = await getAdminSchoolIds(req);
    const teachers = await prisma.teacher.findMany({
      where: { schoolId: { in: schoolIds } },
      select: {
        id: true,
        firstName: true,
        lastName: true,
        email: true,
        role: true,
        status: true,
        schoolId: true,
        createdAt: true,
      },
      orderBy: { createdAt: "desc" },
    });
    res.json({ success: true, teachers });
  }),
);

export { router as adminRouter };
