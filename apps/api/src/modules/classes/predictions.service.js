import crypto from "node:crypto";

import { prisma } from "../../db/prisma.js";
import { env } from "../../config/env.js";
import { createAnalysisReport } from "../reports/analysis-report.service.js";
import { sendUrgentStaffAlert } from "../predictions/staff-alert.service.js";
import { publishNotification } from "../../realtime/notifications.js";

function payloadFor(observation, student) {
  return {
    student_key: student.studentKey,
    school_id: observation.schoolId,
    academic_year: observation.academicYear,
    term: observation.term,
    week: observation.week,
    grade_level: observation.gradeLevel,
    attendance_rate_term_to_date: observation.attendanceRateTermToDate,
    attendance_rate_last_4w: observation.attendanceRateLast4w,
    attendance_rate_prior_term: observation.attendanceRatePriorTerm,
    attendance_trend_4w: observation.attendanceTrend4w,
    consecutive_absences: observation.consecutiveAbsences,
    longest_absence_streak_term: observation.longestAbsenceStreakTerm,
    absences_prior_year: observation.absencesPriorYear,
    ...(observation.weeklyAttendanceHistory?.length
      ? { weekly_attendance_history: observation.weeklyAttendanceHistory }
      : {}),
    avg_exam_score: observation.avgExamScore,
    avg_exam_score_prev_term: observation.avgExamScorePrevTerm,
    assessment_completion_rate: observation.assessmentCompletionRate,
    core_subject_failures: observation.coreSubjectFailures,
    age_years: observation.ageYears,
    repeated_a_grade: observation.repeatedAGrade,
    school_transfers_count: observation.schoolTransfersCount,
    bece_registered: observation.beceRegistered,
    fee_status: observation.feeStatus,
    fee_arrears_terms: observation.feeArrearsTerms,
    has_textbooks: observation.hasTextbooks,
    has_uniform: observation.hasUniform,
    siblings_in_school: observation.siblingsInSchool,
    does_paid_or_farm_work: observation.doesPaidOrFarmWork,
    guardian_type: observation.guardianType,
    distance_band: observation.distanceBand,
    behaviour_flag: observation.behaviourFlag,
    behaviour_incidents_term: observation.behaviourIncidentsTerm,
    health_absence_days_term: observation.healthAbsenceDaysTerm,
    sex: observation.sex,
    region: observation.region,
    poverty_quintile: observation.povertyQuintile,
  };
}

async function scoreOne(observation, student, model) {
  const body = JSON.stringify(payloadFor(observation, student));
  const timestamp = String(Date.now());
  const message = `edutrace-api.${timestamp}.${body}`;
  const signature = crypto
    .createHmac("sha256", env.ML_SERVICE_SHARED_SECRET)
    .update(message)
    .digest("hex");
  const response = await fetch(`${env.ML_SERVICE_URL}/v1/score`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": process.env.EDUTRACE_API_KEY || "dev_demo_key_change_me",
      "X-Service-Id": "edutrace-api",
      "X-Service-Timestamp": timestamp,
      "X-Service-Signature": signature,
    },
    body,
  });
  if (!response.ok) throw new Error(`ML service returned ${response.status}`);
  const result = await response.json();
  if (result.model_version !== model.modelVersion)
    throw new Error("ML service model does not match the active registration.");
  return result;
}

export async function scoreClass(
  classId,
  schoolId,
  generatedById = null,
  teacherContact = null,
) {
  const model = await prisma.modelRegistration.findFirst({
    where: { status: "ACTIVE" },
    orderBy: { activatedAt: "desc" },
  });
  if (!model) return { status: "MODEL_UNAVAILABLE", scored: 0, failed: 0 };
  const observations = await prisma.studentObservation.findMany({
    where: { schoolId, student: { classId }, riskAssessment: null },
    include: { student: true },
  });
  let scored = 0;
  let failed = 0;
  for (const observation of observations) {
    try {
      const result = await scoreOne(observation, observation.student, model);
      await prisma.riskAssessment.upsert({
        where: { observationId: observation.id },
        create: {
          schoolId,
          studentId: observation.studentId,
          observationId: observation.id,
          modelRegistrationId: model.id,
          risk: result.risk,
          tier: result.tier,
          percentileInCohort: result.percentile_in_cohort,
          drivers: result.drivers,
          protective: result.protective,
          recourse: result.recourse,
          narrative: result.narrative,
          requiresHumanReview: result.requires_human_review,
          latencyMs: result.latency_ms,
        },
        update: {
          modelRegistrationId: model.id,
          risk: result.risk,
          tier: result.tier,
          percentileInCohort: result.percentile_in_cohort,
          drivers: result.drivers,
          protective: result.protective,
          recourse: result.recourse,
          narrative: result.narrative,
          requiresHumanReview: result.requires_human_review,
          latencyMs: result.latency_ms,
          scoredAt: new Date(),
        },
      });
      scored += 1;
    } catch {
      failed += 1;
    }
  }
  let reportId = null;
  if (generatedById && scored > 0) {
    const assessments = await prisma.riskAssessment.findMany({
      where: { schoolId, student: { classId }, modelRegistrationId: model.id },
      include: { student: { include: { identity: true } } },
      orderBy: { risk: "desc" },
    });
    const report = await createAnalysisReport({
      schoolId,
      generatedById,
      source: "CLASS_ANALYSIS",
      summary: {
        rows_in: observations.length,
        rows_scored: scored,
        model_version: model.modelVersion,
      },
      worklist: assessments.map((assessment) => ({
        observation_id: assessment.observationId,
        student_key: assessment.student.studentKey,
        risk: assessment.risk,
        tier: assessment.tier,
        drivers: assessment.drivers,
      })),
    });
    reportId = report.id;
    const urgentCount = assessments.filter(
      (assessment) => assessment.tier === "HIGH",
    ).length;
    if (urgentCount && teacherContact?.phone) {
      try {
        await sendUrgentStaffAlert({
          teacherMsisdn: teacherContact.phone,
          schoolName: teacherContact.schoolName,
          urgentCount,
          schoolId,
          teacherId: generatedById,
        });
      } catch {
        // Preserve the successful analysis if SMS delivery is unavailable.
      }
    }
    if (urgentCount) {
      const highRiskStudents = assessments
        .filter((assessment) => assessment.tier === "HIGH")
        .map(
          (assessment) =>
            assessment.student.identity?.studentName ||
            assessment.student.studentKey,
        );
      await publishNotification(schoolId, {
        type: "URGENT_SUPPORT",
        teacherId: generatedById,
        urgentCount,
        highRiskStudents,
        message: `Urgent-support students need review today: ${highRiskStudents.join(", ")}.`,
        createdAt: new Date().toISOString(),
      });
    }
  }
  return {
    status: failed && !scored ? "ML_UNAVAILABLE" : "COMPLETED",
    scored,
    failed,
    modelVersion: model.modelVersion,
    reportId,
  };
}
