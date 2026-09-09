import crypto from "node:crypto";
import { Router } from "express";
import multer from "multer";
import Papa from "papaparse";
import { z } from "zod";

import { env } from "../../config/env.js";
import {
  ForbiddenError,
  AppError,
  ValidationError,
} from "../../middleware/errorHandler.js";
import { asyncHandler } from "../../utils/asyncHandler.js";
import { requireAuth } from "../auth/auth.middleware.js";
import {
  createAnalysisReport,
  normalizeWorklist,
} from "../reports/analysis-report.service.js";
import { sendUrgentStaffAlert } from "./staff-alert.service.js";
import { publishNotification } from "../../realtime/notifications.js";

const router = Router();
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 10 * 1024 * 1024, files: 1 },
});
const requiredHeaders = [
  "student_key",
  "school_id",
  "academic_year",
  "term",
  "week",
  "grade_level",
];
const allowedGrades = new Set(["JHS1", "JHS2", "JHS3"]);
const allowedTerms = new Set(["T1", "T2", "T3"]);

function validateModelCsv(buffer, schoolIds) {
  const parsed = Papa.parse(buffer.toString("utf8"), {
    header: true,
    skipEmptyLines: true,
    transformHeader: (header) => header.replace(/^\uFEFF/, "").trim(),
  });
  if (parsed.errors.length)
    throw new ValidationError(
      "The scoring CSV could not be parsed.",
      parsed.errors,
    );
  const fields = parsed.meta.fields || [];
  const missing = requiredHeaders.filter((header) => !fields.includes(header));
  if (missing.length)
    throw new ValidationError("The scoring CSV is missing model columns.", {
      missing,
      received: fields,
    });
  if (!parsed.data.length)
    throw new ValidationError("The scoring CSV contains no rows.");

  const errors = [];
  const studentKeys = new Set();
  parsed.data.forEach((row, index) => {
    const rowNumber = index + 2;
    if (!row.student_key?.trim())
      errors.push({
        row: rowNumber,
        field: "student_key",
        message: "Student key is required.",
      });
    if (!schoolIds.includes(row.school_id))
      errors.push({
        row: rowNumber,
        field: "school_id",
        message: "The row belongs to a different school.",
      });
    if (!allowedGrades.has(row.grade_level))
      errors.push({
        row: rowNumber,
        field: "grade_level",
        message: "Expected JHS1, JHS2, or JHS3.",
      });
    if (!allowedTerms.has(row.term))
      errors.push({
        row: rowNumber,
        field: "term",
        message: "Expected T1, T2, or T3.",
      });
    if (studentKeys.has(row.student_key))
      errors.push({
        row: rowNumber,
        field: "student_key",
        message: "Duplicate student key in this file.",
      });
    studentKeys.add(row.student_key);
  });
  if (errors.length)
    throw new ValidationError("The scoring CSV contains invalid rows.", errors);
}

async function forwardToModel(file, capacity) {
  const target = `${env.ML_SERVICE_URL}/v1/score/batch?capacity=${capacity}`;
  const form = new FormData();
  form.append(
    "file",
    new Blob([file.buffer], { type: "text/csv" }),
    file.originalname,
  );
  const request = new Request(target, { method: "POST", body: form });
  const body = Buffer.from(await request.arrayBuffer());
  const timestamp = String(Date.now());
  const message = `edutrace-api.${timestamp}.${body.toString("binary")}`;
  const signature = crypto
    .createHmac("sha256", env.ML_SERVICE_SHARED_SECRET)
    .update(message, "binary")
    .digest("hex");
  let response;
  try {
    response = await fetch(target, {
      method: "POST",
      headers: {
        "Content-Type": request.headers.get("content-type"),
        "X-API-Key": env.ML_SERVICE_API_KEY,
        "X-Service-Id": "edutrace-api",
        "X-Service-Timestamp": timestamp,
        "X-Service-Signature": signature,
      },
      body,
    });
  } catch {
    throw new AppError(
      "Risk analysis is unavailable. Start the ML service and try again.",
      { statusCode: 503, code: "ML_SERVICE_UNAVAILABLE", details: { target } },
    );
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new ValidationError(
      payload.detail || "The ML service could not score this file.",
      payload,
    );
  return payload;
}

router.use(requireAuth);
router.post(
  "/batch",
  upload.single("file"),
  asyncHandler(async (req, res) => {
    if (!req.auth.schoolId)
      throw new ForbiddenError("Your account is not linked to a school.");
    if (!req.file)
      throw new ValidationError("Choose a model scoring CSV to upload.");
    const capacity = z.coerce
      .number()
      .int()
      .min(1)
      .max(500)
      .parse(req.query.capacity || 40);
    const schoolIds = [
      req.auth.schoolId,
      req.auth.teacher?.school?.schoolCode,
    ].filter(Boolean);
    validateModelCsv(req.file.buffer, schoolIds);
    const result = await forwardToModel(req.file, capacity);
    const worklist = normalizeWorklist(result.worklist);
    const report = await createAnalysisReport({
      schoolId: req.auth.schoolId,
      generatedById: req.auth.teacherId,
      source: "BATCH_CSV",
      filename: req.file.originalname,
      summary: result.summary,
      worklist,
    });
    let staffAlert = { attempted: false, accepted: false };
    const urgentCount = worklist.filter((item) => item.tier === "HIGH").length;
    if (urgentCount && req.auth.teacher?.phone) {
      try {
        staffAlert = await sendUrgentStaffAlert({
          teacherMsisdn: req.auth.teacher.phone,
          schoolName: req.auth.teacher.school?.name,
          urgentCount,
          schoolId: req.auth.schoolId,
          teacherId: req.auth.teacherId,
        });
      } catch {
        staffAlert = {
          attempted: true,
          accepted: false,
          reason: "Arkesel delivery failed",
        };
      }
    }
    if (urgentCount) {
      const highRiskKeys = worklist
        .filter((item) => item.tier === "HIGH")
        .map((item) => item.student_key);
      const highRiskRecords = await prisma.student.findMany({
        where: {
          schoolId: req.auth.schoolId,
          studentKey: { in: highRiskKeys },
        },
        select: {
          studentKey: true,
          identity: { select: { studentName: true } },
        },
      });
      const names = new Map(
        highRiskRecords.map((student) => [
          student.studentKey,
          student.identity?.studentName || student.studentKey,
        ]),
      );
      const highRiskStudents = highRiskKeys.map((key) => names.get(key) || key);
      await publishNotification(req.auth.schoolId, {
        type: "URGENT_SUPPORT",
        teacherId: req.auth.teacherId,
        urgentCount,
        highRiskStudents,
        message: `Urgent-support students need review today: ${highRiskStudents.join(", ")}.`,
        createdAt: new Date().toISOString(),
      });
    }
    res.json({
      success: true,
      ...result,
      worklist,
      reportId: report.id,
      staffAlert,
    });
  }),
);

export { router as predictionsRouter };
