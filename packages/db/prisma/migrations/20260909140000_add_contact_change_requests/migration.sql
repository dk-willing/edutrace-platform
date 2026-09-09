CREATE TYPE "ContactChangeStatus" AS ENUM ('PENDING', 'APPROVED', 'REJECTED');

CREATE TABLE "ContactChangeRequest" (
    "id" TEXT NOT NULL,
    "teacherId" TEXT NOT NULL,
    "oldEmail" TEXT NOT NULL,
    "requestedEmail" TEXT,
    "requestedPhone" TEXT,
    "status" "ContactChangeStatus" NOT NULL DEFAULT 'PENDING',
    "reviewedById" TEXT,
    "reviewedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "ContactChangeRequest_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "ContactChangeRequest_teacherId_status_idx" ON "ContactChangeRequest"("teacherId", "status");
CREATE INDEX "ContactChangeRequest_status_createdAt_idx" ON "ContactChangeRequest"("status", "createdAt");
ALTER TABLE "ContactChangeRequest" ADD CONSTRAINT "ContactChangeRequest_teacherId_fkey" FOREIGN KEY ("teacherId") REFERENCES "Teacher"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "ContactChangeRequest" ADD CONSTRAINT "ContactChangeRequest_reviewedById_fkey" FOREIGN KEY ("reviewedById") REFERENCES "Teacher"("id") ON DELETE SET NULL ON UPDATE CASCADE;