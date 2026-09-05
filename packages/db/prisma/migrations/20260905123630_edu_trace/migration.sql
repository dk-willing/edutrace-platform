-- CreateEnum
CREATE TYPE "TeacherRole" AS ENUM ('TEACHER', 'SCHOOL_ADMIN', 'SYSTEM_ADMIN', 'DISTRICT_ADMIN', 'SUPER_ADMIN');

-- CreateEnum
CREATE TYPE "AccountStatus" AS ENUM ('PENDING_EMAIL_VERIFICATION', 'PENDING_SCHOOL_APPROVAL', 'ACTIVE', 'SUSPENDED', 'DEACTIVATED');

-- CreateEnum
CREATE TYPE "SchoolStatus" AS ENUM ('ONBOARDING', 'ACTIVE', 'SUSPENDED', 'ARCHIVED');

-- CreateEnum
CREATE TYPE "GradeLevel" AS ENUM ('JHS1', 'JHS2', 'JHS3');

-- CreateEnum
CREATE TYPE "Term" AS ENUM ('T1', 'T2', 'T3');

-- CreateEnum
CREATE TYPE "RiskTier" AS ENUM ('LOW', 'WATCH', 'ELEVATED', 'HIGH');

-- CreateEnum
CREATE TYPE "ModelStatus" AS ENUM ('DEVELOPMENT', 'VALIDATION', 'APPROVED', 'ACTIVE', 'RETIRED');

-- CreateEnum
CREATE TYPE "ReviewDecision" AS ENUM ('CONFIRM', 'DISMISS', 'ESCALATE', 'DEFER');

-- CreateEnum
CREATE TYPE "OverrideReason" AS ENUM ('ALREADY_TRANSFERRED', 'ABSENCE_EXPLAINED_ILLNESS', 'ABSENCE_EXPLAINED_BEREAVEMENT', 'ABSENCE_EXPLAINED_TRAVEL', 'SUPPORT_ALREADY_IN_PLACE', 'LEVIES_WAIVED', 'DATA_ENTRY_ERROR', 'STAFF_CONCERN_NOT_IN_DATA', 'HOUSEHOLD_CIRCUMSTANCES_CHANGED', 'OTHER_RECORDED_OFFLINE');

-- CreateEnum
CREATE TYPE "SafeguardingCategory" AS ENUM ('IMMEDIATE_SAFETY', 'HARM_TO_SELF', 'ABUSE_OR_NEGLECT', 'EXPLOITATION_OR_CHILD_LABOUR', 'PREGNANCY_OR_PARENTING', 'HEALTH_NEEDS_REFERRAL', 'OTHER_WELFARE_CONCERN');

-- CreateEnum
CREATE TYPE "SafeguardingReferral" AS ENUM ('HEAD_TEACHER', 'SCHOOL_GC_COORDINATOR', 'DISTRICT_GC_COORDINATOR', 'DEPT_SOCIAL_WELFARE', 'POLICE_DOVVSU', 'GHANA_HEALTH_SERVICE');

-- CreateEnum
CREATE TYPE "NotificationChannel" AS ENUM ('NONE', 'SMS', 'SMS_PLUS_CALL');

-- CreateEnum
CREATE TYPE "UploadStatus" AS ENUM ('RECEIVED', 'VALIDATING', 'AWAITING_MODEL_APPROVAL', 'SCORING', 'COMPLETED', 'FAILED');

-- CreateEnum
CREATE TYPE "InterventionStatus" AS ENUM ('PROPOSED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED');

-- CreateTable
CREATE TABLE "School" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "schoolCode" TEXT NOT NULL,
    "registrationNumber" TEXT,
    "district" TEXT NOT NULL,
    "region" TEXT NOT NULL,
    "address" TEXT,
    "contactEmail" TEXT,
    "contactPhone" TEXT,
    "status" "SchoolStatus" NOT NULL DEFAULT 'ONBOARDING',
    "onboardingNotes" TEXT,
    "onboardedByAdminId" TEXT,
    "smsPerTermCapDefault" INTEGER NOT NULL DEFAULT 3,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "School_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Teacher" (
    "id" TEXT NOT NULL,
    "schoolId" TEXT,
    "firstName" TEXT NOT NULL,
    "lastName" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "phone" TEXT,
    "passwordHash" TEXT NOT NULL,
    "role" "TeacherRole" NOT NULL DEFAULT 'TEACHER',
    "status" "AccountStatus" NOT NULL DEFAULT 'PENDING_EMAIL_VERIFICATION',
    "emailVerified" BOOLEAN NOT NULL DEFAULT false,
    "phoneVerified" BOOLEAN NOT NULL DEFAULT false,
    "approvedByAdminId" TEXT,
    "approvedAt" TIMESTAMP(3),
    "lastLoginAt" TIMESTAMP(3),
    "failedLoginCount" INTEGER NOT NULL DEFAULT 0,
    "lockedUntil" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Teacher_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "RefreshToken" (
    "id" TEXT NOT NULL,
    "teacherId" TEXT NOT NULL,
    "tokenHash" TEXT NOT NULL,
    "issuedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "revokedAt" TIMESTAMP(3),
    "replacedByTokenId" TEXT,

    CONSTRAINT "RefreshToken_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "EmailVerificationToken" (
    "id" TEXT NOT NULL,
    "teacherId" TEXT NOT NULL,
    "tokenHash" TEXT NOT NULL,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "usedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "EmailVerificationToken_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "PasswordResetToken" (
    "id" TEXT NOT NULL,
    "teacherId" TEXT NOT NULL,
    "tokenHash" TEXT NOT NULL,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "usedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "PasswordResetToken_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Class" (
    "id" TEXT NOT NULL,
    "schoolId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "gradeLevel" "GradeLevel" NOT NULL,
    "academicYear" INTEGER NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Class_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Student" (
    "id" TEXT NOT NULL,
    "schoolId" TEXT NOT NULL,
    "classId" TEXT,
    "studentKey" TEXT NOT NULL,
    "gradeLevel" "GradeLevel" NOT NULL,
    "externalId" TEXT,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Student_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "StudentIdentity" (
    "id" TEXT NOT NULL,
    "studentId" TEXT NOT NULL,
    "studentName" TEXT NOT NULL,
    "guardianName" TEXT,
    "guardianMsisdn" TEXT,
    "dateOfBirth" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "StudentIdentity_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "StudentObservation" (
    "id" TEXT NOT NULL,
    "schoolId" TEXT NOT NULL,
    "studentId" TEXT NOT NULL,
    "academicYear" INTEGER NOT NULL,
    "term" "Term" NOT NULL,
    "week" INTEGER NOT NULL,
    "gradeLevel" "GradeLevel" NOT NULL,
    "attendanceRateTermToDate" DOUBLE PRECISION,
    "attendanceRateLast4w" DOUBLE PRECISION,
    "attendanceRatePriorTerm" DOUBLE PRECISION,
    "attendanceTrend4w" DOUBLE PRECISION,
    "consecutiveAbsences" INTEGER,
    "longestAbsenceStreakTerm" INTEGER,
    "absencesPriorYear" INTEGER,
    "weeklyAttendanceHistory" DOUBLE PRECISION[],
    "avgExamScore" DOUBLE PRECISION,
    "avgExamScorePrevTerm" DOUBLE PRECISION,
    "assessmentCompletionRate" DOUBLE PRECISION,
    "coreSubjectFailures" INTEGER,
    "ageYears" DOUBLE PRECISION,
    "repeatedAGrade" BOOLEAN,
    "schoolTransfersCount" INTEGER,
    "beceRegistered" BOOLEAN,
    "feeStatus" TEXT,
    "feeArrearsTerms" INTEGER,
    "hasTextbooks" BOOLEAN,
    "hasUniform" BOOLEAN,
    "siblingsInSchool" INTEGER,
    "doesPaidOrFarmWork" BOOLEAN,
    "guardianType" TEXT,
    "distanceBand" TEXT,
    "behaviourFlag" TEXT,
    "behaviourIncidentsTerm" INTEGER,
    "healthAbsenceDaysTerm" INTEGER,
    "sex" TEXT,
    "region" TEXT,
    "povertyQuintile" INTEGER,
    "sourceUploadId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "StudentObservation_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "TrainingDatasetRecord" (
    "id" TEXT NOT NULL,
    "datasetName" TEXT NOT NULL,
    "datasetVersion" TEXT NOT NULL,
    "sourceObservationHash" TEXT NOT NULL,
    "featureVector" JSONB NOT NULL,
    "label" INTEGER,
    "deidentifiedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "approvedByAdminId" TEXT NOT NULL,
    "qualityCheckPassed" BOOLEAN NOT NULL DEFAULT false,
    "fairnessCheckPassed" BOOLEAN NOT NULL DEFAULT false,
    "provenanceNote" TEXT NOT NULL,

    CONSTRAINT "TrainingDatasetRecord_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "CsvUpload" (
    "id" TEXT NOT NULL,
    "schoolId" TEXT NOT NULL,
    "uploadedById" TEXT NOT NULL,
    "originalFilename" TEXT NOT NULL,
    "storagePath" TEXT NOT NULL,
    "status" "UploadStatus" NOT NULL DEFAULT 'RECEIVED',
    "rowsTotal" INTEGER,
    "rowsAccepted" INTEGER,
    "rowsRejected" INTEGER,
    "errorSummary" JSONB,
    "capacityRequested" INTEGER,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "completedAt" TIMESTAMP(3),

    CONSTRAINT "CsvUpload_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ModelRegistration" (
    "id" TEXT NOT NULL,
    "modelVersion" TEXT NOT NULL,
    "contractFingerprint" TEXT NOT NULL,
    "dataProvenance" TEXT NOT NULL,
    "trainingDatasetId" TEXT,
    "trainedAt" TIMESTAMP(3) NOT NULL,
    "status" "ModelStatus" NOT NULL DEFAULT 'DEVELOPMENT',
    "evaluationMetrics" JSONB NOT NULL,
    "knownLimitations" TEXT[],
    "outOfScope" TEXT[],
    "approvedByAdminId" TEXT,
    "approvedAt" TIMESTAMP(3),
    "approvalNote" TEXT,
    "activatedAt" TIMESTAMP(3),
    "retiredAt" TIMESTAMP(3),
    "firstSeenAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ModelRegistration_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "RiskAssessment" (
    "id" TEXT NOT NULL,
    "schoolId" TEXT NOT NULL,
    "studentId" TEXT NOT NULL,
    "observationId" TEXT NOT NULL,
    "modelRegistrationId" TEXT NOT NULL,
    "risk" DOUBLE PRECISION NOT NULL,
    "tier" "RiskTier" NOT NULL,
    "percentileInCohort" DOUBLE PRECISION,
    "drivers" JSONB NOT NULL,
    "protective" JSONB NOT NULL,
    "recourse" JSONB NOT NULL,
    "narrative" TEXT NOT NULL,
    "requiresHumanReview" BOOLEAN NOT NULL DEFAULT true,
    "isDemo" BOOLEAN NOT NULL DEFAULT false,
    "scoredAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "latencyMs" DOUBLE PRECISION,

    CONSTRAINT "RiskAssessment_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ReviewOutcome" (
    "id" TEXT NOT NULL,
    "riskAssessmentId" TEXT NOT NULL,
    "reviewerId" TEXT NOT NULL,
    "reviewerRole" TEXT NOT NULL,
    "decision" "ReviewDecision" NOT NULL,
    "reason" "OverrideReason",
    "adjustTierBy" INTEGER NOT NULL DEFAULT 0,
    "modelTier" "RiskTier" NOT NULL,
    "finalTier" "RiskTier" NOT NULL,
    "overridden" BOOLEAN NOT NULL DEFAULT false,
    "notificationUnlocked" BOOLEAN NOT NULL DEFAULT false,
    "note" TEXT,
    "reviewedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ReviewOutcome_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "NeedsProfile" (
    "id" TEXT NOT NULL,
    "schoolId" TEXT NOT NULL,
    "studentId" TEXT NOT NULL,
    "conductedById" TEXT NOT NULL,
    "domainsPresent" TEXT[],
    "agreedActions" JSONB NOT NULL,
    "escalationRaised" BOOLEAN NOT NULL DEFAULT false,
    "conductedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "affectsRiskScore" BOOLEAN NOT NULL DEFAULT false,

    CONSTRAINT "NeedsProfile_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "SafeguardingEscalation" (
    "id" TEXT NOT NULL,
    "schoolId" TEXT NOT NULL,
    "studentId" TEXT NOT NULL,
    "category" "SafeguardingCategory" NOT NULL,
    "raisedById" TEXT NOT NULL,
    "referredTo" "SafeguardingReferral"[],
    "conversationStopped" BOOLEAN NOT NULL DEFAULT true,
    "learnerInformed" BOOLEAN NOT NULL DEFAULT true,
    "followUpDue" TIMESTAMP(3),
    "raisedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "SafeguardingEscalation_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "NotificationLog" (
    "id" TEXT NOT NULL,
    "schoolId" TEXT NOT NULL,
    "studentId" TEXT NOT NULL,
    "channel" "NotificationChannel" NOT NULL,
    "templateKey" TEXT,
    "segments" INTEGER,
    "encoding" TEXT,
    "provider" TEXT,
    "providerMessageId" TEXT,
    "accepted" BOOLEAN,
    "suppressedReason" TEXT,
    "sentAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "NotificationLog_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "CallTask" (
    "id" TEXT NOT NULL,
    "studentId" TEXT NOT NULL,
    "assignedToId" TEXT,
    "reason" TEXT NOT NULL,
    "completed" BOOLEAN NOT NULL DEFAULT false,
    "outcome" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "completedAt" TIMESTAMP(3),

    CONSTRAINT "CallTask_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Intervention" (
    "id" TEXT NOT NULL,
    "schoolId" TEXT NOT NULL,
    "studentId" TEXT NOT NULL,
    "ownedById" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    "status" "InterventionStatus" NOT NULL DEFAULT 'PROPOSED',
    "dueAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Intervention_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "InterventionFollowUp" (
    "id" TEXT NOT NULL,
    "interventionId" TEXT NOT NULL,
    "note" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "InterventionFollowUp_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "AuditLog" (
    "id" TEXT NOT NULL,
    "schoolId" TEXT,
    "actorId" TEXT,
    "event" TEXT NOT NULL,
    "payload" JSONB NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "AuditLog_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "School_schoolCode_key" ON "School"("schoolCode");

-- CreateIndex
CREATE INDEX "School_district_idx" ON "School"("district");

-- CreateIndex
CREATE INDEX "School_region_idx" ON "School"("region");

-- CreateIndex
CREATE INDEX "School_status_idx" ON "School"("status");

-- CreateIndex
CREATE UNIQUE INDEX "Teacher_email_key" ON "Teacher"("email");

-- CreateIndex
CREATE INDEX "Teacher_schoolId_idx" ON "Teacher"("schoolId");

-- CreateIndex
CREATE INDEX "Teacher_role_idx" ON "Teacher"("role");

-- CreateIndex
CREATE INDEX "Teacher_status_idx" ON "Teacher"("status");

-- CreateIndex
CREATE UNIQUE INDEX "RefreshToken_tokenHash_key" ON "RefreshToken"("tokenHash");

-- CreateIndex
CREATE INDEX "RefreshToken_teacherId_idx" ON "RefreshToken"("teacherId");

-- CreateIndex
CREATE UNIQUE INDEX "EmailVerificationToken_tokenHash_key" ON "EmailVerificationToken"("tokenHash");

-- CreateIndex
CREATE INDEX "EmailVerificationToken_teacherId_idx" ON "EmailVerificationToken"("teacherId");

-- CreateIndex
CREATE UNIQUE INDEX "PasswordResetToken_tokenHash_key" ON "PasswordResetToken"("tokenHash");

-- CreateIndex
CREATE INDEX "PasswordResetToken_teacherId_idx" ON "PasswordResetToken"("teacherId");

-- CreateIndex
CREATE INDEX "Class_schoolId_idx" ON "Class"("schoolId");

-- CreateIndex
CREATE UNIQUE INDEX "Class_schoolId_name_academicYear_key" ON "Class"("schoolId", "name", "academicYear");

-- CreateIndex
CREATE UNIQUE INDEX "Student_studentKey_key" ON "Student"("studentKey");

-- CreateIndex
CREATE INDEX "Student_schoolId_idx" ON "Student"("schoolId");

-- CreateIndex
CREATE INDEX "Student_classId_idx" ON "Student"("classId");

-- CreateIndex
CREATE UNIQUE INDEX "StudentIdentity_studentId_key" ON "StudentIdentity"("studentId");

-- CreateIndex
CREATE INDEX "StudentObservation_schoolId_idx" ON "StudentObservation"("schoolId");

-- CreateIndex
CREATE INDEX "StudentObservation_studentId_idx" ON "StudentObservation"("studentId");

-- CreateIndex
CREATE INDEX "StudentObservation_schoolId_academicYear_term_week_idx" ON "StudentObservation"("schoolId", "academicYear", "term", "week");

-- CreateIndex
CREATE UNIQUE INDEX "StudentObservation_studentId_academicYear_term_week_key" ON "StudentObservation"("studentId", "academicYear", "term", "week");

-- CreateIndex
CREATE INDEX "TrainingDatasetRecord_datasetName_datasetVersion_idx" ON "TrainingDatasetRecord"("datasetName", "datasetVersion");

-- CreateIndex
CREATE INDEX "CsvUpload_schoolId_idx" ON "CsvUpload"("schoolId");

-- CreateIndex
CREATE INDEX "CsvUpload_status_idx" ON "CsvUpload"("status");

-- CreateIndex
CREATE UNIQUE INDEX "ModelRegistration_modelVersion_key" ON "ModelRegistration"("modelVersion");

-- CreateIndex
CREATE INDEX "ModelRegistration_status_idx" ON "ModelRegistration"("status");

-- CreateIndex
CREATE UNIQUE INDEX "RiskAssessment_observationId_key" ON "RiskAssessment"("observationId");

-- CreateIndex
CREATE INDEX "RiskAssessment_schoolId_idx" ON "RiskAssessment"("schoolId");

-- CreateIndex
CREATE INDEX "RiskAssessment_studentId_idx" ON "RiskAssessment"("studentId");

-- CreateIndex
CREATE INDEX "RiskAssessment_schoolId_tier_idx" ON "RiskAssessment"("schoolId", "tier");

-- CreateIndex
CREATE INDEX "RiskAssessment_scoredAt_idx" ON "RiskAssessment"("scoredAt");

-- CreateIndex
CREATE UNIQUE INDEX "ReviewOutcome_riskAssessmentId_key" ON "ReviewOutcome"("riskAssessmentId");

-- CreateIndex
CREATE INDEX "ReviewOutcome_reviewerId_idx" ON "ReviewOutcome"("reviewerId");

-- CreateIndex
CREATE INDEX "NeedsProfile_schoolId_idx" ON "NeedsProfile"("schoolId");

-- CreateIndex
CREATE INDEX "NeedsProfile_studentId_idx" ON "NeedsProfile"("studentId");

-- CreateIndex
CREATE INDEX "SafeguardingEscalation_schoolId_idx" ON "SafeguardingEscalation"("schoolId");

-- CreateIndex
CREATE INDEX "SafeguardingEscalation_studentId_idx" ON "SafeguardingEscalation"("studentId");

-- CreateIndex
CREATE INDEX "SafeguardingEscalation_category_idx" ON "SafeguardingEscalation"("category");

-- CreateIndex
CREATE INDEX "NotificationLog_schoolId_idx" ON "NotificationLog"("schoolId");

-- CreateIndex
CREATE INDEX "NotificationLog_studentId_idx" ON "NotificationLog"("studentId");

-- CreateIndex
CREATE INDEX "CallTask_studentId_idx" ON "CallTask"("studentId");

-- CreateIndex
CREATE INDEX "CallTask_assignedToId_idx" ON "CallTask"("assignedToId");

-- CreateIndex
CREATE INDEX "Intervention_schoolId_idx" ON "Intervention"("schoolId");

-- CreateIndex
CREATE INDEX "Intervention_studentId_idx" ON "Intervention"("studentId");

-- CreateIndex
CREATE INDEX "Intervention_status_idx" ON "Intervention"("status");

-- CreateIndex
CREATE INDEX "InterventionFollowUp_interventionId_idx" ON "InterventionFollowUp"("interventionId");

-- CreateIndex
CREATE INDEX "AuditLog_schoolId_idx" ON "AuditLog"("schoolId");

-- CreateIndex
CREATE INDEX "AuditLog_event_idx" ON "AuditLog"("event");

-- CreateIndex
CREATE INDEX "AuditLog_createdAt_idx" ON "AuditLog"("createdAt");

-- AddForeignKey
ALTER TABLE "Teacher" ADD CONSTRAINT "Teacher_schoolId_fkey" FOREIGN KEY ("schoolId") REFERENCES "School"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "RefreshToken" ADD CONSTRAINT "RefreshToken_teacherId_fkey" FOREIGN KEY ("teacherId") REFERENCES "Teacher"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "EmailVerificationToken" ADD CONSTRAINT "EmailVerificationToken_teacherId_fkey" FOREIGN KEY ("teacherId") REFERENCES "Teacher"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "PasswordResetToken" ADD CONSTRAINT "PasswordResetToken_teacherId_fkey" FOREIGN KEY ("teacherId") REFERENCES "Teacher"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Class" ADD CONSTRAINT "Class_schoolId_fkey" FOREIGN KEY ("schoolId") REFERENCES "School"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Student" ADD CONSTRAINT "Student_schoolId_fkey" FOREIGN KEY ("schoolId") REFERENCES "School"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Student" ADD CONSTRAINT "Student_classId_fkey" FOREIGN KEY ("classId") REFERENCES "Class"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "StudentIdentity" ADD CONSTRAINT "StudentIdentity_studentId_fkey" FOREIGN KEY ("studentId") REFERENCES "Student"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "StudentObservation" ADD CONSTRAINT "StudentObservation_schoolId_fkey" FOREIGN KEY ("schoolId") REFERENCES "School"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "StudentObservation" ADD CONSTRAINT "StudentObservation_studentId_fkey" FOREIGN KEY ("studentId") REFERENCES "Student"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "StudentObservation" ADD CONSTRAINT "StudentObservation_sourceUploadId_fkey" FOREIGN KEY ("sourceUploadId") REFERENCES "CsvUpload"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "CsvUpload" ADD CONSTRAINT "CsvUpload_schoolId_fkey" FOREIGN KEY ("schoolId") REFERENCES "School"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "CsvUpload" ADD CONSTRAINT "CsvUpload_uploadedById_fkey" FOREIGN KEY ("uploadedById") REFERENCES "Teacher"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "RiskAssessment" ADD CONSTRAINT "RiskAssessment_schoolId_fkey" FOREIGN KEY ("schoolId") REFERENCES "School"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "RiskAssessment" ADD CONSTRAINT "RiskAssessment_studentId_fkey" FOREIGN KEY ("studentId") REFERENCES "Student"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "RiskAssessment" ADD CONSTRAINT "RiskAssessment_observationId_fkey" FOREIGN KEY ("observationId") REFERENCES "StudentObservation"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "RiskAssessment" ADD CONSTRAINT "RiskAssessment_modelRegistrationId_fkey" FOREIGN KEY ("modelRegistrationId") REFERENCES "ModelRegistration"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ReviewOutcome" ADD CONSTRAINT "ReviewOutcome_riskAssessmentId_fkey" FOREIGN KEY ("riskAssessmentId") REFERENCES "RiskAssessment"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ReviewOutcome" ADD CONSTRAINT "ReviewOutcome_reviewerId_fkey" FOREIGN KEY ("reviewerId") REFERENCES "Teacher"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "NeedsProfile" ADD CONSTRAINT "NeedsProfile_schoolId_fkey" FOREIGN KEY ("schoolId") REFERENCES "School"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "NeedsProfile" ADD CONSTRAINT "NeedsProfile_studentId_fkey" FOREIGN KEY ("studentId") REFERENCES "Student"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "NeedsProfile" ADD CONSTRAINT "NeedsProfile_conductedById_fkey" FOREIGN KEY ("conductedById") REFERENCES "Teacher"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "SafeguardingEscalation" ADD CONSTRAINT "SafeguardingEscalation_schoolId_fkey" FOREIGN KEY ("schoolId") REFERENCES "School"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "SafeguardingEscalation" ADD CONSTRAINT "SafeguardingEscalation_studentId_fkey" FOREIGN KEY ("studentId") REFERENCES "Student"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "SafeguardingEscalation" ADD CONSTRAINT "SafeguardingEscalation_raisedById_fkey" FOREIGN KEY ("raisedById") REFERENCES "Teacher"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "NotificationLog" ADD CONSTRAINT "NotificationLog_schoolId_fkey" FOREIGN KEY ("schoolId") REFERENCES "School"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "NotificationLog" ADD CONSTRAINT "NotificationLog_studentId_fkey" FOREIGN KEY ("studentId") REFERENCES "Student"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "CallTask" ADD CONSTRAINT "CallTask_studentId_fkey" FOREIGN KEY ("studentId") REFERENCES "Student"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "CallTask" ADD CONSTRAINT "CallTask_assignedToId_fkey" FOREIGN KEY ("assignedToId") REFERENCES "Teacher"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Intervention" ADD CONSTRAINT "Intervention_schoolId_fkey" FOREIGN KEY ("schoolId") REFERENCES "School"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Intervention" ADD CONSTRAINT "Intervention_studentId_fkey" FOREIGN KEY ("studentId") REFERENCES "Student"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Intervention" ADD CONSTRAINT "Intervention_ownedById_fkey" FOREIGN KEY ("ownedById") REFERENCES "Teacher"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "InterventionFollowUp" ADD CONSTRAINT "InterventionFollowUp_interventionId_fkey" FOREIGN KEY ("interventionId") REFERENCES "Intervention"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "AuditLog" ADD CONSTRAINT "AuditLog_schoolId_fkey" FOREIGN KEY ("schoolId") REFERENCES "School"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "AuditLog" ADD CONSTRAINT "AuditLog_actorId_fkey" FOREIGN KEY ("actorId") REFERENCES "Teacher"("id") ON DELETE SET NULL ON UPDATE CASCADE;
