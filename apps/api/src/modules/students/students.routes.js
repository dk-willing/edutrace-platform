import { Router } from "express";
import { z } from "zod";

import { prisma } from "../../db/prisma.js";
import { ForbiddenError } from "../../middleware/errorHandler.js";
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

router.use(requireAuth);

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
