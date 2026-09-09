import { Router } from "express";
import { z } from "zod";

import { prisma } from "../../db/prisma.js";
import {
  ConflictError,
  ForbiddenError,
  NotFoundError,
} from "../../middleware/errorHandler.js";
import { asyncHandler } from "../../utils/asyncHandler.js";
import { requireAuth } from "../auth/auth.middleware.js";

const router = Router();
const querySchema = z.object({
  search: z.string().trim().max(100).optional(),
  classId: z.string().trim().optional(),
  gradeLevel: z.enum(["JHS1", "JHS2", "JHS3"]).optional(),
  page: z.coerce.number().int().min(1).default(1),
  pageSize: z.coerce.number().int().min(1).max(100).default(25),
});
const studentUpdateSchema = z.object({
  studentName: z.string().trim().min(1).max(160).optional(),
  externalId: z.string().trim().max(80).nullable().optional(),
  guardianName: z.string().trim().max(160).nullable().optional(),
  guardianMsisdn: z.string().trim().max(32).nullable().optional(),
  gradeLevel: z.enum(["JHS1", "JHS2", "JHS3"]).optional(),
  classId: z.string().trim().min(1).nullable().optional(),
});
const reviewSchema = z.object({
  decision: z.enum(["CONFIRM", "DISMISS", "ESCALATE", "DEFER"]),
  note: z.string().trim().max(1000).nullable().optional(),
});

router.use(requireAuth);

async function getManagedStudent(req, studentId) {
  if (!req.auth.schoolId)
    throw new ForbiddenError("Your account is not linked to a school.");
  const student = await prisma.student.findFirst({
    where: {
      id: studentId,
      schoolId: req.auth.schoolId,
      ...(req.auth.role === "TEACHER"
        ? { class: { ownerId: req.auth.teacherId } }
        : {}),
    },
    include: { identity: true, class: true },
  });
  if (!student) throw new NotFoundError("Student not found.");
  return student;
}

router.get(
  "/:studentId",
  asyncHandler(async (req, res) => {
    const student = await getManagedStudent(req, req.params.studentId);
    const [latestObservation, latestAssessment] = await prisma.$transaction([
      prisma.studentObservation.findFirst({
        where: { studentId: student.id },
        orderBy: [{ academicYear: "desc" }, { term: "desc" }, { week: "desc" }],
      }),
      prisma.riskAssessment.findFirst({
        where: { studentId: student.id },
        orderBy: { scoredAt: "desc" },
        include: {
          modelRegistration: { select: { modelVersion: true } },
          reviewOutcome: true,
        },
      }),
    ]);
    if (latestAssessment && !latestAssessment.reviewViewedAt) {
      latestAssessment.reviewViewedAt = new Date();
      await prisma.riskAssessment.update({
        where: { id: latestAssessment.id },
        data: { reviewViewedAt: latestAssessment.reviewViewedAt },
      });
    }
    res.json({ success: true, student, latestObservation, latestAssessment });
  }),
);

router.post(
  "/:studentId/assessment/review",
  asyncHandler(async (req, res) => {
    const student = await getManagedStudent(req, req.params.studentId);
    const input = reviewSchema.parse(req.body);
    const assessment = await prisma.riskAssessment.findFirst({
      where: { studentId: student.id },
      orderBy: { scoredAt: "desc" },
    });
    if (!assessment)
      throw new NotFoundError("This student has no risk assessment to review.");
    const reviewOutcome = await prisma.reviewOutcome.upsert({
      where: { riskAssessmentId: assessment.id },
      create: {
        riskAssessmentId: assessment.id,
        reviewerId: req.auth.teacherId,
        reviewerRole: req.auth.role,
        decision: input.decision,
        modelTier: assessment.tier,
        finalTier: assessment.tier,
        note: input.note || null,
      },
      update: {
        reviewerId: req.auth.teacherId,
        reviewerRole: req.auth.role,
        decision: input.decision,
        modelTier: assessment.tier,
        finalTier: assessment.tier,
        note: input.note || null,
        reviewedAt: new Date(),
      },
    });
    res.json({ success: true, reviewOutcome });
  }),
);

router.patch(
  "/:studentId",
  asyncHandler(async (req, res) => {
    const student = await getManagedStudent(req, req.params.studentId);
    const input = studentUpdateSchema.parse(req.body);
    if (input.classId !== undefined && input.classId !== null) {
      const targetClass = await prisma.class.findFirst({
        where: {
          id: input.classId,
          schoolId: req.auth.schoolId,
          ...(req.auth.role === "TEACHER"
            ? { ownerId: req.auth.teacherId }
            : {}),
        },
      });
      if (!targetClass)
        throw new ForbiddenError(
          "You cannot assign this student to that class.",
        );
    }
    if (input.externalId) {
      const targetClassId = input.classId ?? student.classId;
      const duplicate = await prisma.student.findFirst({
        where: {
          id: { not: student.id },
          schoolId: req.auth.schoolId,
          classId: targetClassId,
          externalId: input.externalId,
          isActive: true,
        },
      });
      if (duplicate)
        throw new ConflictError(
          "That external ID is already used in this class.",
        );
    }
    const updated = await prisma.$transaction(async (tx) => {
      const result = await tx.student.update({
        where: { id: student.id },
        data: {
          ...(input.externalId !== undefined
            ? { externalId: input.externalId || null }
            : {}),
          ...(input.gradeLevel ? { gradeLevel: input.gradeLevel } : {}),
          ...(input.classId !== undefined ? { classId: input.classId } : {}),
          identity: {
            update: {
              ...(input.studentName !== undefined
                ? { studentName: input.studentName }
                : {}),
              ...(input.guardianName !== undefined
                ? { guardianName: input.guardianName || null }
                : {}),
              ...(input.guardianMsisdn !== undefined
                ? { guardianMsisdn: input.guardianMsisdn || null }
                : {}),
            },
          },
        },
        include: { identity: true, class: true },
      });
      await tx.auditLog.create({
        data: {
          schoolId: req.auth.schoolId,
          actorId: req.auth.teacherId,
          event: "STUDENT_UPDATED",
          payload: { studentId: student.id },
        },
      });
      return result;
    });
    res.json({ success: true, student: updated });
  }),
);

router.delete(
  "/:studentId",
  asyncHandler(async (req, res) => {
    const student = await getManagedStudent(req, req.params.studentId);
    await prisma.$transaction([
      prisma.student.update({
        where: { id: student.id },
        data: { isActive: false },
      }),
      prisma.auditLog.create({
        data: {
          schoolId: req.auth.schoolId,
          actorId: req.auth.teacherId,
          event: "STUDENT_DEACTIVATED",
          payload: { studentId: student.id },
        },
      }),
    ]);
    res.json({ success: true, studentId: student.id });
  }),
);

router.get(
  "/",
  asyncHandler(async (req, res) => {
    if (!req.auth.schoolId)
      throw new ForbiddenError("Your account is not linked to a school.");
    const { search, classId, gradeLevel, page, pageSize } = querySchema.parse(
      req.query,
    );
    const where = {
      schoolId: req.auth.schoolId,
      isActive: true,
      ...(req.auth.role === "TEACHER"
        ? { class: { ownerId: req.auth.teacherId } }
        : {}),
      ...(classId ? { classId } : {}),
      ...(gradeLevel ? { gradeLevel } : {}),
      ...(search
        ? {
            OR: [
              { externalId: { contains: search, mode: "insensitive" } },
              {
                identity: {
                  studentName: { contains: search, mode: "insensitive" },
                },
              },
            ],
          }
        : {}),
    };
    const [students, total] = await prisma.$transaction([
      prisma.student.findMany({
        where,
        include: { identity: true, class: true },
        orderBy: { createdAt: "desc" },
        skip: (page - 1) * pageSize,
        take: pageSize,
      }),
      prisma.student.count({ where }),
    ]);
    res.json({
      success: true,
      students,
      pagination: { page, pageSize, total, pages: Math.ceil(total / pageSize) },
    });
  }),
);

export { router as studentsRouter };
