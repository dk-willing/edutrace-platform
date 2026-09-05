import { Router } from "express";

import { prisma } from "../../db/prisma.js";
import { ForbiddenError } from "../../middleware/errorHandler.js";
import { asyncHandler } from "../../utils/asyncHandler.js";
import { requireAuth } from "../auth/auth.middleware.js";

const router = Router();
router.use(requireAuth);

router.get(
  "/school",
  asyncHandler(async (req, res) => {
    if (!req.auth.schoolId)
      throw new ForbiddenError("Your account is not linked to a school.");
    const classWhere = {
      schoolId: req.auth.schoolId,
      ...(req.auth.role === "TEACHER" ? { ownerId: req.auth.teacherId } : {}),
    };
    const classes = await prisma.class.findMany({
      where: classWhere,
      select: { id: true, name: true },
    });
    const classIds = classes.map((classItem) => classItem.id);
    const scope = classIds.length
      ? { student: { classId: { in: classIds } } }
      : { id: "__empty_report__" };
    const [students, assessments, tiers, observations] =
      await prisma.$transaction([
        prisma.student.count({
          where: {
            schoolId: req.auth.schoolId,
            isActive: true,
            ...(classIds.length
              ? { classId: { in: classIds } }
              : { id: "__empty_students__" }),
          },
        }),
        prisma.riskAssessment.count({
          where: { schoolId: req.auth.schoolId, ...scope },
        }),
        prisma.riskAssessment.groupBy({
          by: ["tier"],
          where: { schoolId: req.auth.schoolId, ...scope },
          _count: { _all: true },
        }),
        prisma.studentObservation.count({
          where: {
            schoolId: req.auth.schoolId,
            ...(classIds.length
              ? { student: { classId: { in: classIds } } }
              : { id: "__empty_observations__" }),
          },
        }),
      ]);
    const activeModel = assessments
      ? await prisma.riskAssessment.findFirst({
          where: { schoolId: req.auth.schoolId, ...scope },
          orderBy: { scoredAt: "desc" },
          select: {
            modelRegistration: { select: { modelVersion: true, status: true } },
          },
        })
      : null;
    res.json({
      success: true,
      report: {
        generatedAt: new Date().toISOString(),
        classes,
        students,
        observations,
        assessments,
        model: activeModel?.modelRegistration || null,
        riskDistribution: Object.fromEntries(
          tiers.map((tier) => [tier.tier, tier._count._all]),
        ),
      },
      availability: assessments ? "AVAILABLE" : "NO_RECORDED_ASSESSMENTS",
    });
  }),
);

export { router as reportsRouter };
