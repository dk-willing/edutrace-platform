import { Router } from "express";

import { prisma } from "../../db/prisma.js";
import { ForbiddenError } from "../../middleware/errorHandler.js";
import { asyncHandler } from "../../utils/asyncHandler.js";
import { requireAuth } from "../auth/auth.middleware.js";

const router = Router();
router.use(requireAuth);

router.get(
  "/",
  asyncHandler(async (req, res) => {
    if (!req.auth.schoolId)
      throw new ForbiddenError("Your account is not linked to a school.");
    const classWhere = {
      schoolId: req.auth.schoolId,
      ...(req.auth.role === "TEACHER" ? { ownerId: req.auth.teacherId } : {}),
    };
    const classes = await prisma.class.findMany({
      where: classWhere,
      select: { id: true, name: true, gradeLevel: true, academicYear: true },
    });
    const classIds = classes.map((classItem) => classItem.id);
    const studentWhere = {
      schoolId: req.auth.schoolId,
      isActive: true,
      ...(classIds.length
        ? { classId: { in: classIds } }
        : { id: "__no_students__" }),
    };
    const [
      studentCount,
      riskGroups,
      reviewCount,
      interventionCount,
      recentAssessments,
    ] = await prisma.$transaction([
      prisma.student.count({ where: studentWhere }),
      prisma.riskAssessment.groupBy({
        by: ["tier"],
        where: {
          schoolId: req.auth.schoolId,
          ...(classIds.length
            ? { student: { classId: { in: classIds } } }
            : { id: "__no_assessments__" }),
        },
        _count: { _all: true },
      }),
      prisma.riskAssessment.count({
        where: {
          schoolId: req.auth.schoolId,
          requiresHumanReview: true,
          reviewOutcome: null,
          ...(classIds.length
            ? { student: { classId: { in: classIds } } }
            : { id: "__no_reviews__" }),
        },
      }),
      prisma.intervention.count({
        where: {
          schoolId: req.auth.schoolId,
          status: { in: ["PROPOSED", "IN_PROGRESS"] },
          ...(req.auth.role === "TEACHER"
            ? { ownedById: req.auth.teacherId }
            : {}),
        },
      }),
      prisma.riskAssessment.findMany({
        where: {
          schoolId: req.auth.schoolId,
          ...(classIds.length
            ? { student: { classId: { in: classIds } } }
            : { id: "__no_recent__" }),
        },
        orderBy: { scoredAt: "desc" },
        take: 8,
        include: {
          student: { include: { identity: true, class: true } },
          modelRegistration: { select: { modelVersion: true } },
        },
      }),
    ]);
    const riskDistribution = Object.fromEntries(
      riskGroups.map((group) => [group.tier, group._count._all]),
    );
    res.json({
      success: true,
      classes,
      stats: {
        studentCount,
        classCount: classes.length,
        awaitingReview: reviewCount,
        openInterventions: interventionCount,
        riskDistribution,
      },
      recentAssessments,
    });
  }),
);

export { router as dashboardRouter };
