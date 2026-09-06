import { Router } from "express";

import { prisma } from "../../db/prisma.js";
import { ForbiddenError } from "../../middleware/errorHandler.js";
import { asyncHandler } from "../../utils/asyncHandler.js";
import { requireAuth } from "../auth/auth.middleware.js";
import { reportPdf } from "./analysis-report.service.js";

const router = Router();
router.use(requireAuth);

router.get(
  "/analysis",
  asyncHandler(async (req, res) => {
    if (!req.auth.schoolId)
      throw new ForbiddenError("Your account is not linked to a school.");
    const reports = await prisma.analysisReport.findMany({
      where: { schoolId: req.auth.schoolId },
      orderBy: { createdAt: "desc" },
      take: 100,
      select: {
        id: true,
        source: true,
        filename: true,
        modelVersion: true,
        totalRows: true,
        rowsScored: true,
        highCount: true,
        tierCounts: true,
        createdAt: true,
      },
    });
    res.json({ success: true, reports });
  }),
);

router.get(
  "/analysis/:reportId/download",
  asyncHandler(async (req, res) => {
    if (!req.auth.schoolId)
      throw new ForbiddenError("Your account is not linked to a school.");
    const report = await prisma.analysisReport.findFirst({
      where: { id: req.params.reportId, schoolId: req.auth.schoolId },
    });
    if (!report)
      return res.status(404).json({
        success: false,
        error: { code: "NOT_FOUND", message: "Report not found." },
      });
    res.set({
      "Content-Type": "application/pdf",
      "Content-Disposition": `attachment; filename="edutrace-report-${report.id}.pdf"`,
    });
    res.send(reportPdf(report));
  }),
);

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
    const activeModel =
      assessments > 0
        ? await prisma.riskAssessment.findFirst({
            where: { schoolId: req.auth.schoolId, ...scope },
            orderBy: { scoredAt: "desc" },
            select: {
              modelRegistration: {
                select: { modelVersion: true, status: true },
              },
            },
          })
        : null;
    const [analysisReportCount, latestAnalysis] = await prisma.$transaction([
      prisma.analysisReport.count({ where: { schoolId: req.auth.schoolId } }),
      prisma.analysisReport.findFirst({
        where: { schoolId: req.auth.schoolId },
        orderBy: { createdAt: "desc" },
        select: {
          id: true,
          source: true,
          filename: true,
          modelVersion: true,
          totalRows: true,
          rowsScored: true,
          highCount: true,
          tierCounts: true,
          createdAt: true,
        },
      }),
    ]);
    res.json({
      success: true,
      report: {
        generatedAt: new Date().toISOString(),
        classes,
        students,
        observations,
        assessments,
        analysisReportCount,
        latestAnalysis,
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
