import crypto from "node:crypto";
import { Router } from "express";
import { z } from "zod";

import { prisma } from "../../db/prisma.js";
import {
  ConflictError,
  ForbiddenError,
  NotFoundError,
} from "../../middleware/errorHandler.js";
import { requireAuth } from "../auth/auth.middleware.js";
import { asyncHandler } from "../../utils/asyncHandler.js";
import { scoreClass } from "./predictions.service.js";

const router = Router();
const classSchema = z.object({
  name: z.string().trim().min(1).max(100),
  gradeLevel: z.enum(["JHS1", "JHS2", "JHS3"]),
  academicYear: z.number().int().min(2000).max(2200),
});
const studentSchema = z.object({
  studentName: z.string().trim().min(1).max(160),
  gradeLevel: z.enum(["JHS1", "JHS2", "JHS3"]),
  externalId: z.string().trim().max(80).optional(),
  guardianName: z.string().trim().max(160).optional(),
  guardianMsisdn: z.string().trim().max(32).optional(),
});

router.use(requireAuth);

function canManageClass(auth, classRecord) {
  return (
    auth.role === "SYSTEM_ADMIN" ||
    auth.role === "SCHOOL_ADMIN" ||
    classRecord.ownerId === auth.teacherId
  );
}

async function getClassForSchool(id, schoolId) {
  const classRecord = await prisma.class.findFirst({ where: { id, schoolId } });
  if (!classRecord) throw new NotFoundError("Class not found.");
  return classRecord;
}

router.get(
  "/",
  asyncHandler(async (req, res) => {
    if (!req.auth.schoolId)
      throw new ForbiddenError("Your account is not linked to a school.");
    const where = { schoolId: req.auth.schoolId };
    if (req.auth.role === "TEACHER") where.ownerId = req.auth.teacherId;
    const classes = await prisma.class.findMany({
      where,
      include: { _count: { select: { students: true } } },
      orderBy: [{ academicYear: "desc" }, { name: "asc" }],
    });
    res.json({ success: true, classes });
  }),
);

router.post(
  "/",
  asyncHandler(async (req, res) => {
    if (!req.auth.schoolId)
      throw new ForbiddenError("Your account is not linked to a school.");
    const input = classSchema.parse(req.body);
    try {
      const classRecord = await prisma.class.create({
        data: {
          ...input,
          schoolId: req.auth.schoolId,
          ownerId: req.auth.teacherId,
        },
        include: { _count: { select: { students: true } } },
      });
      await prisma.auditLog.create({
        data: {
          schoolId: req.auth.schoolId,
          actorId: req.auth.teacherId,
          event: "CLASS_CREATED",
          payload: { classId: classRecord.id },
        },
      });
      res.status(201).json({ success: true, class: classRecord });
    } catch (error) {
      if (error.code === "P2002")
        throw new ConflictError(
          "You already have a class with that name for this academic year.",
        );
      throw error;
    }
  }),
);

router.get(
  "/:classId/students",
  asyncHandler(async (req, res) => {
    const classRecord = await getClassForSchool(
      req.params.classId,
      req.auth.schoolId,
    );
    if (!canManageClass(req.auth, classRecord))
      throw new ForbiddenError("You cannot access this class.");
    const students = await prisma.student.findMany({
      where: {
        schoolId: req.auth.schoolId,
        classId: classRecord.id,
        isActive: true,
      },
      include: { identity: true },
      orderBy: { createdAt: "desc" },
    });
    res.json({ success: true, class: classRecord, students });
  }),
);

router.post(
  "/:classId/students",
  asyncHandler(async (req, res) => {
    const classRecord = await getClassForSchool(
      req.params.classId,
      req.auth.schoolId,
    );
    if (!canManageClass(req.auth, classRecord))
      throw new ForbiddenError("You cannot manage this class.");
    const input = studentSchema.parse(req.body);
    if (input.externalId) {
      const duplicate = await prisma.student.findFirst({
        where: {
          schoolId: req.auth.schoolId,
          externalId: input.externalId,
          isActive: true,
        },
      });
      if (duplicate)
        throw new ConflictError(
          "A student with that external ID already exists in this school.",
        );
    }
    const student = await prisma.student.create({
      data: {
        schoolId: req.auth.schoolId,
        classId: classRecord.id,
        studentKey: crypto.randomBytes(18).toString("hex"),
        gradeLevel: input.gradeLevel,
        externalId: input.externalId || null,
        identity: {
          create: {
            studentName: input.studentName,
            guardianName: input.guardianName || null,
            guardianMsisdn: input.guardianMsisdn || null,
          },
        },
      },
      include: { identity: true, class: true },
    });
    await prisma.auditLog.create({
      data: {
        schoolId: req.auth.schoolId,
        actorId: req.auth.teacherId,
        event: "STUDENT_CREATED",
        payload: { studentId: student.id, classId: classRecord.id },
      },
    });
    res.status(201).json({ success: true, student });
  }),
);

router.get(
  "/:classId/predictions",
  asyncHandler(async (req, res) => {
    const classRecord = await getClassForSchool(
      req.params.classId,
      req.auth.schoolId,
    );
    if (!canManageClass(req.auth, classRecord))
      throw new ForbiddenError("You cannot access this class.");
    const assessments = await prisma.riskAssessment.findMany({
      where: {
        schoolId: req.auth.schoolId,
        student: { classId: classRecord.id },
      },
      include: {
        student: { include: { identity: true } },
        modelRegistration: { select: { modelVersion: true } },
      },
      orderBy: { risk: "desc" },
    });
    res.json({ success: true, class: classRecord, assessments });
  }),
);

router.post(
  "/:classId/predictions/retry",
  asyncHandler(async (req, res) => {
    const classRecord = await getClassForSchool(
      req.params.classId,
      req.auth.schoolId,
    );
    if (!canManageClass(req.auth, classRecord))
      throw new ForbiddenError("You cannot manage this class.");
    const result = await scoreClass(
      classRecord.id,
      req.auth.schoolId,
      req.auth.teacherId,
      {
        phone: req.auth.teacher?.phone,
        schoolName: req.auth.teacher?.school?.name,
      },
    );
    res.json({ success: true, ...result });
  }),
);

export { router as classesRouter };
