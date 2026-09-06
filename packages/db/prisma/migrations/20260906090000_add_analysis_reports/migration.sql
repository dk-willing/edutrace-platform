CREATE TABLE "AnalysisReport" (
    "id" TEXT NOT NULL,
    "schoolId" TEXT NOT NULL,
    "generatedById" TEXT NOT NULL,
    "source" TEXT NOT NULL,
    "filename" TEXT,
    "modelVersion" TEXT,
    "totalRows" INTEGER NOT NULL,
    "rowsScored" INTEGER NOT NULL,
    "highCount" INTEGER NOT NULL DEFAULT 0,
    "tierCounts" JSONB NOT NULL,
    "results" JSONB NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "AnalysisReport_pkey" PRIMARY KEY ("id")
);
CREATE INDEX "AnalysisReport_schoolId_createdAt_idx" ON "AnalysisReport"("schoolId", "createdAt");
CREATE INDEX "AnalysisReport_generatedById_idx" ON "AnalysisReport"("generatedById");
ALTER TABLE "AnalysisReport" ADD CONSTRAINT "AnalysisReport_schoolId_fkey" FOREIGN KEY ("schoolId") REFERENCES "School"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "AnalysisReport" ADD CONSTRAINT "AnalysisReport_generatedById_fkey" FOREIGN KEY ("generatedById") REFERENCES "Teacher"("id") ON DELETE RESTRICT ON UPDATE CASCADE;