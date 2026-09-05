import { Router } from "express";
import multer from "multer";
import Papa from "papaparse";
import { z } from "zod";

import { prisma } from "../../db/prisma.js";
import {
  ForbiddenError,
  NotFoundError,
  ValidationError,
} from "../../middleware/errorHandler.js";
import { asyncHandler } from "../../utils/asyncHandler.js";
import { requireAuth } from "../auth/auth.middleware.js";

const router = Router();
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 10 * 1024 * 1024, files: 1 },
});
const requiredHeaders = ["studentName", "gradeLevel"];
const allowedGrades = new Set(["JHS1", "JHS2", "JHS3"]);

function number(value, field, row, { min = -Infinity, max = Infinity } = {}) {
  if (value === undefined || value === "") return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < min || parsed > max)
    throw new Error(
      `Row ${row}: ${field} must be a number between ${min} and ${max}.`,
    );
  return parsed;
}
function rate(value, field, row) {
  const parsed = number(value, field, row, { min: 0, max: 100 });
  return parsed === null ? null : parsed <= 1 ? parsed * 100 : parsed;
}
function bool(value, field, row) {
  if (value === undefined || value === "") return null;
  if (["true", "1", "yes"].includes(String(value).toLowerCase())) return true;
  if (["false", "0", "no"].includes(String(value).toLowerCase())) return false;
  throw new Error(`Row ${row}: ${field} must be true or false.`);
}

router.use(requireAuth);

router.get(
  "/",
  asyncHandler(async (req, res) => {
    if (!req.auth.schoolId)
      throw new ForbiddenError("Your account is not linked to a school.");
    const uploads = await prisma.csvUpload.findMany({
      where: { schoolId: req.auth.schoolId },
      include: { class: { select: { name: true } } },
      orderBy: { createdAt: "desc" },
      take: 50,
    });
    res.json({ success: true, uploads });
  }),
);

router.post(
  "/",
  upload.single("file"),
  asyncHandler(async (req, res) => {
    if (!req.auth.schoolId)
      throw new ForbiddenError("Your account is not linked to a school.");
    if (!req.file) throw new ValidationError("Choose a CSV file to upload.");
    const classId = z.string().min(1).parse(req.body.classId);
    const classRecord = await prisma.class.findFirst({
      where: {
        id: classId,
        schoolId: req.auth.schoolId,
        ...(req.auth.role === "TEACHER" ? { ownerId: req.auth.teacherId } : {}),
      },
    });
    if (!classRecord)
      throw new NotFoundError(
        "That class was not found or is not assigned to you.",
      );

    const parsed = Papa.parse(req.file.buffer.toString("utf8"), {
      header: true,
      skipEmptyLines: true,
      transformHeader: (header) => header.trim(),
    });
    if (parsed.errors.length)
      throw new ValidationError("The CSV could not be parsed.", parsed.errors);
    const headers = parsed.meta.fields || [];
    const missing = requiredHeaders.filter(
      (header) => !headers.includes(header),
    );
    if (missing.length)
      throw new ValidationError(
        `Missing required CSV column${missing.length === 1 ? "" : "s"}: ${missing.join(", ")}.`,
      );

    const uploadRecord = await prisma.csvUpload.create({
      data: {
        schoolId: req.auth.schoolId,
        uploadedById: req.auth.teacherId,
        classId,
        originalFilename: req.file.originalname,
        storagePath: `memory://${req.file.originalname}`,
        status: "VALIDATING",
        rowsTotal: parsed.data.length,
      },
    });
    const accepted = [];
    const errors = [];
    const seenIds = new Set();
    parsed.data.forEach((row, index) => {
      const rowNumber = index + 2;
      try {
        const studentName = String(row.studentName || "").trim();
        const gradeLevel = String(row.gradeLevel || "")
          .trim()
          .toUpperCase();
        if (!studentName)
          throw new Error(`Row ${rowNumber}: studentName is required.`);
        if (!allowedGrades.has(gradeLevel))
          throw new Error(
            `Row ${rowNumber}: gradeLevel must be JHS1, JHS2, or JHS3.`,
          );
        const externalId = String(row.externalId || "").trim() || null;
        if (externalId && seenIds.has(externalId))
          throw new Error(
            `Row ${rowNumber}: duplicate externalId ${externalId} in this file.`,
          );
        if (externalId) seenIds.add(externalId);
        accepted.push({ row, studentName, gradeLevel, externalId, rowNumber });
      } catch (error) {
        errors.push(error.message);
      }
    });

    try {
      await prisma.$transaction(async (tx) => {
        for (const item of accepted) {
          const student = await tx.student.create({
            data: {
              schoolId: req.auth.schoolId,
              classId,
              studentKey: `${req.auth.schoolId}:${item.externalId || `${uploadRecord.id}:${item.rowNumber}`}`,
              externalId: item.externalId,
              gradeLevel: item.gradeLevel,
              identity: {
                create: {
                  studentName: item.studentName,
                  guardianName: rowValue(item.row, "guardianName"),
                  guardianMsisdn: rowValue(item.row, "guardianMsisdn"),
                },
              },
            },
          });
          await tx.studentObservation.create({
            data: {
              schoolId: req.auth.schoolId,
              studentId: student.id,
              academicYear: new Date().getFullYear(),
              term: "T1",
              week: 1,
              gradeLevel: item.gradeLevel,
              attendanceRateTermToDate: rate(
                item.row.attendanceRateTermToDate,
                "attendanceRateTermToDate",
                item.rowNumber,
              ),
              attendanceRateLast4w: rate(
                item.row.attendanceRateLast4w,
                "attendanceRateLast4w",
                item.rowNumber,
              ),
              avgExamScore: rate(
                item.row.avgExamScore,
                "avgExamScore",
                item.rowNumber,
              ),
              assessmentCompletionRate: rate(
                item.row.assessmentCompletionRate,
                "assessmentCompletionRate",
                item.rowNumber,
              ),
              coreSubjectFailures: number(
                item.row.coreSubjectFailures,
                "coreSubjectFailures",
                item.rowNumber,
                { min: 0, max: 12 },
              ),
              feeStatus: rowValue(item.row, "feeStatus"),
              hasTextbooks: bool(
                item.row.hasTextbooks,
                "hasTextbooks",
                item.rowNumber,
              ),
              hasUniform: bool(
                item.row.hasUniform,
                "hasUniform",
                item.rowNumber,
              ),
              doesPaidOrFarmWork: bool(
                item.row.doesPaidOrFarmWork,
                "doesPaidOrFarmWork",
                item.rowNumber,
              ),
              distanceBand: rowValue(item.row, "distanceBand"),
              weeklyAttendanceHistory: [],
              sourceUploadId: uploadRecord.id,
            },
          });
        }
        await tx.csvUpload.update({
          where: { id: uploadRecord.id },
          data: {
            status: "COMPLETED",
            rowsAccepted: accepted.length,
            rowsRejected: errors.length,
            errorSummary: errors.length ? errors : undefined,
            completedAt: new Date(),
          },
        });
      });
    } catch (error) {
      await prisma.csvUpload.update({
        where: { id: uploadRecord.id },
        data: {
          status: "FAILED",
          rowsAccepted: 0,
          rowsRejected: parsed.data.length,
          errorSummary: [error.message],
        },
      });
      throw error;
    }
    res
      .status(201)
      .json({
        success: true,
        upload: {
          id: uploadRecord.id,
          filename: req.file.originalname,
          classId,
          rowsTotal: parsed.data.length,
          rowsAccepted: accepted.length,
          rowsRejected: errors.length,
          errors,
        },
      });
  }),
);

function rowValue(row, key) {
  const value = row[key];
  return value === undefined || value === "" ? null : String(value).trim();
}
export { router as importsRouter };
