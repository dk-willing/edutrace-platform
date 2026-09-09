import crypto from "node:crypto";
import { Router } from "express";
import multer from "multer";
import Papa from "papaparse";
import { z } from "zod";

import { prisma } from "../../db/prisma.js";
import {
  ConflictError,
  ForbiddenError,
  NotFoundError,
  ValidationError,
} from "../../middleware/errorHandler.js";
import { asyncHandler } from "../../utils/asyncHandler.js";
import { requireAuth } from "../auth/auth.middleware.js";
import { scoreClass } from "../classes/predictions.service.js";

const router = Router();
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 10 * 1024 * 1024, files: 1 },
});
const headers = [
  "studentName",
  "gradeLevel",
  "externalId",
  "guardianName",
  "guardianMsisdn",
  "attendanceRateTermToDate",
  "attendanceRateLast4w",
  "avgExamScore",
  "assessmentCompletionRate",
  "coreSubjectFailures",
  "feeStatus",
  "hasTextbooks",
  "hasUniform",
  "doesPaidOrFarmWork",
  "distanceBand",
];
const requiredHeaders = ["studentName", "gradeLevel"];
const headerAliases = {
  student_name: "studentName",
  student_external_id: "externalId",
  grade_level: "gradeLevel",
  guardian_name: "guardianName",
  guardian_msisdn: "guardianMsisdn",
  attendance_rate_term_to_date: "attendanceRateTermToDate",
  attendance_rate_last_4w: "attendanceRateLast4w",
  avg_exam_score: "avgExamScore",
  assessment_completion_rate: "assessmentCompletionRate",
  core_subject_failures: "coreSubjectFailures",
  fee_status: "feeStatus",
  has_textbooks: "hasTextbooks",
  has_uniform: "hasUniform",
  does_paid_or_farm_work: "doesPaidOrFarmWork",
  distance_band: "distanceBand",
};
const grades = new Set(["JHS1", "JHS2", "JHS3"]);
const numericFields = new Set([
  "attendanceRateTermToDate",
  "attendanceRateLast4w",
  "avgExamScore",
  "assessmentCompletionRate",
]);
const booleanFields = new Set([
  "hasTextbooks",
  "hasUniform",
  "doesPaidOrFarmWork",
]);

function value(row, field) {
  const raw = row[field];
  return raw === undefined || raw === null || String(raw).trim() === ""
    ? null
    : String(raw).trim();
}
function parseBoolean(raw, field, row) {
  if (raw === null) return null;
  if (["true", "TRUE", "1", "yes", "YES"].includes(raw)) return true;
  if (["false", "FALSE", "0", "no", "NO"].includes(raw)) return false;
  throw { field, row, message: "Expected true or false." };
}
function parseNumber(raw, field, row, range, integer = false) {
  if (raw === null) return null;
  const parsed = Number(raw);
  if (
    !Number.isFinite(parsed) ||
    (integer && !Number.isInteger(parsed)) ||
    parsed < range[0] ||
    parsed > range[1]
  )
    throw {
      field,
      row,
      message: `Expected a ${integer ? "whole number" : "number"} from ${range[0]} to ${range[1]}.`,
    };
  return parsed;
}
function parseRate(raw, field, row) {
  const parsed = parseNumber(raw, field, row, [0, 100]);
  return parsed !== null && parsed <= 1 ? parsed * 100 : parsed;
}
function parseRow(row, rowNumber) {
  const parsed = {};
  for (const field of headers) parsed[field] = value(row, field);
  for (const [field, max] of Object.entries({
    studentName: 120,
    externalId: 64,
    guardianName: 120,
    guardianMsisdn: 20,
  })) {
    if (parsed[field] !== null && parsed[field].length > max)
      throw {
        field,
        row: rowNumber,
        message: `Must be ${max} characters or fewer.`,
      };
  }
  if (!parsed.studentName)
    throw {
      field: "studentName",
      row: rowNumber,
      message: "Student name is required.",
    };
  if (!grades.has(parsed.gradeLevel))
    throw {
      field: "gradeLevel",
      row: rowNumber,
      message: "Expected JHS1, JHS2, or JHS3.",
    };
  for (const field of numericFields)
    parsed[field] = parseRate(parsed[field], field, rowNumber);
  if (parsed.coreSubjectFailures !== null)
    parsed.coreSubjectFailures = parseNumber(
      parsed.coreSubjectFailures,
      "coreSubjectFailures",
      rowNumber,
      [0, 12],
      true,
    );
  for (const field of booleanFields)
    parsed[field] = parseBoolean(parsed[field], field, rowNumber);
  return parsed;
}
function parseCsv(buffer) {
  const result = Papa.parse(buffer.toString("utf8"), {
    header: true,
    skipEmptyLines: true,
    transformHeader: (header) => {
      const normalized = header.replace(/^\uFEFF/, "").trim();
      return headerAliases[normalized] || normalized;
    },
  });
  if (result.errors.length)
    throw new ValidationError(
      "The CSV could not be parsed.",
      result.errors.map((error) => ({
        message: error.message,
        row: error.row,
      })),
    );
  const actual = result.meta.fields || [];
  const missing = requiredHeaders.filter((header) => !actual.includes(header));
  const duplicates = actual.filter(
    (header, index) => actual.indexOf(header) !== index,
  );
  if (missing.length || duplicates.length)
    throw new ValidationError(
      "CSV headers do not match the official EduTrace template.",
      { missing, duplicates, received: actual },
    );
  if (!result.data.length)
    throw new ValidationError("The CSV contains no student rows.");
  const rows = [];
  const errors = [];
  const seen = new Set();
  for (const [index, row] of result.data.entries()) {
    const rowNumber = index + 2;
    try {
      const parsed = parseRow(row, rowNumber);
      if (parsed.externalId && seen.has(parsed.externalId))
        throw {
          field: "externalId",
          row: rowNumber,
          message: "Duplicate external ID in this upload.",
        };
      if (parsed.externalId) seen.add(parsed.externalId);
      rows.push(parsed);
    } catch (error) {
      errors.push(
        error.field
          ? error
          : { field: "row", row: rowNumber, message: "Malformed row." },
      );
    }
  }
  return { rows, errors, totalRows: result.data.length };
}
async function getClass(req, classId) {
  if (!req.auth.schoolId)
    throw new ForbiddenError("Your account is not linked to a school.");
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
  return classRecord;
}

router.use(requireAuth);
router.get("/template", (_req, res) => {
  const examples = [
    [
      "Amina Mensah",
      "JHS2",
      "DEMO-001",
      "Kofi Mensah",
      "",
      "88",
      "82",
      "92",
      "0",
      "PAID_IN_FULL",
      "true",
      "true",
      "false",
      "M15_TO_30",
    ],
    [
      "Kojo Owusu",
      "JHS2",
      "DEMO-002",
      "Adwoa Owusu",
      "",
      "64",
      "52",
      "67",
      "2",
      "PART_PAID",
      "false",
      "true",
      "true",
      "M30_TO_60",
    ],
  ];
  res
    .type("text/csv")
    .send(
      [
        headers.join(","),
        ...examples.map((row) =>
          row.map((cell) => `"${cell.replaceAll('"', '""')}"`).join(","),
        ),
      ].join("\n"),
    );
});
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
    const classRecord = await getClass(
      req,
      z.string().min(1).parse(req.body.classId),
    );
    if (!req.file) throw new ValidationError("Choose a CSV file to upload.");
    const parsed = parseCsv(req.file.buffer);
    const existing = await prisma.student.findMany({
      where: {
        schoolId: req.auth.schoolId,
        classId: classRecord.id,
        externalId: {
          in: parsed.rows.map((row) => row.externalId).filter(Boolean),
        },
        isActive: true,
      },
      select: { externalId: true, id: true },
    });
    const existingByExternalId = new Map(
      existing.map((item) => [item.externalId, item.id]),
    );
    const record = await prisma.csvUpload.create({
      data: {
        schoolId: req.auth.schoolId,
        uploadedById: req.auth.teacherId,
        classId: classRecord.id,
        originalFilename: req.file.originalname,
        storagePath: "memory://pending",
        status: "AWAITING_MODEL_APPROVAL",
        rowsTotal: parsed.totalRows,
        rowsAccepted: parsed.errors.length ? 0 : parsed.rows.length,
        rowsRejected: parsed.errors.length,
        errorSummary: {
          errors: parsed.errors,
          rows: parsed.errors.length ? [] : parsed.rows,
          existingStudentIds: Object.fromEntries(
            parsed.rows
              .filter(
                (row) =>
                  row.externalId && existingByExternalId.has(row.externalId),
              )
              .map((row) => [
                row.externalId,
                existingByExternalId.get(row.externalId),
              ]),
          ),
        },
      },
    });
    res.status(201).json({
      success: true,
      valid: parsed.errors.length === 0,
      uploadId: record.id,
      totalRows: parsed.totalRows,
      validRows: parsed.errors.length ? 0 : parsed.rows.length,
      invalidRows: parsed.errors.length,
      errors: parsed.errors,
      preview: parsed.errors.length ? [] : parsed.rows.slice(0, 10),
    });
  }),
);
router.post(
  "/:uploadId/commit",
  asyncHandler(async (req, res) => {
    const record = await prisma.csvUpload.findFirst({
      where: {
        id: req.params.uploadId,
        schoolId: req.auth.schoolId,
        uploadedById: req.auth.teacherId,
      },
      include: { class: true },
    });
    if (!record) throw new NotFoundError("Pending import not found.");
    if (record.status !== "AWAITING_MODEL_APPROVAL")
      throw new ConflictError(
        "This import is no longer awaiting confirmation.",
      );
    const snapshot = record.errorSummary?.rows;
    if (!Array.isArray(snapshot) || !snapshot.length)
      throw new ValidationError("This import has no valid rows to commit.");
    const existingStudentIds = record.errorSummary?.existingStudentIds || {};
    const academicYear = new Date().getFullYear();
    const students = await prisma.$transaction(async (tx) => {
      const studentIds = [];
      for (const row of snapshot) {
        const existingId = row.externalId
          ? existingStudentIds[row.externalId]
          : null;
        const studentId = existingId || crypto.randomUUID();
        if (existingId) {
          await tx.student.update({
            where: { id: existingId },
            data: { gradeLevel: row.gradeLevel },
          });
          await tx.studentIdentity.upsert({
            where: { studentId: existingId },
            create: {
              id: crypto.randomUUID(),
              studentId: existingId,
              studentName: row.studentName,
              guardianName: row.guardianName,
              guardianMsisdn: row.guardianMsisdn,
            },
            update: {
              studentName: row.studentName,
              guardianName: row.guardianName,
              guardianMsisdn: row.guardianMsisdn,
            },
          });
        } else {
          await tx.student.create({
            data: {
              id: studentId,
              schoolId: record.schoolId,
              classId: record.classId,
              studentKey: crypto.randomBytes(18).toString("hex"),
              externalId: row.externalId,
              gradeLevel: row.gradeLevel,
              identity: {
                create: {
                  id: crypto.randomUUID(),
                  studentName: row.studentName,
                  guardianName: row.guardianName,
                  guardianMsisdn: row.guardianMsisdn,
                },
              },
            },
          });
        }
        const observation = {
          schoolId: record.schoolId,
          studentId,
          academicYear,
          term: "T1",
          week: 1,
          gradeLevel: row.gradeLevel,
          attendanceRateTermToDate: row.attendanceRateTermToDate,
          attendanceRateLast4w: row.attendanceRateLast4w,
          avgExamScore: row.avgExamScore,
          assessmentCompletionRate: row.assessmentCompletionRate,
          coreSubjectFailures: row.coreSubjectFailures,
          feeStatus: row.feeStatus,
          hasTextbooks: row.hasTextbooks,
          hasUniform: row.hasUniform,
          doesPaidOrFarmWork: row.doesPaidOrFarmWork,
          distanceBand: row.distanceBand,
          weeklyAttendanceHistory: [],
          sourceUploadId: record.id,
        };
        const currentObservation = existingId
          ? await tx.studentObservation.findFirst({
              where: { studentId, academicYear, term: "T1", week: 1 },
              orderBy: { createdAt: "desc" },
            })
          : null;
        if (currentObservation)
          await tx.studentObservation.update({
            where: { id: currentObservation.id },
            data: observation,
          });
        else
          await tx.studentObservation.create({
            data: { id: crypto.randomUUID(), ...observation },
          });
        studentIds.push(studentId);
      }
      await tx.csvUpload.update({
        where: { id: record.id },
        data: {
          status: "COMPLETED",
          completedAt: new Date(),
          errorSummary: { rowCount: studentIds.length },
        },
      });
      await tx.auditLog.create({
        data: {
          schoolId: record.schoolId,
          actorId: req.auth.teacherId,
          event: "STUDENT_IMPORT_COMMITTED",
          payload: { uploadId: record.id, rowCount: studentIds.length },
        },
      });
      return studentIds;
    });
    const analysis = await scoreClass(
      record.classId,
      record.schoolId,
      req.auth.teacherId,
      {
        phone: req.auth.teacher?.phone,
        schoolName: req.auth.teacher?.school?.name,
      },
    );
    res.status(201).json({
      success: true,
      classId: record.classId,
      studentIds: students,
      predictionStatus: analysis.status,
      analysis,
    });
  }),
);
export { router as importsRouter };
