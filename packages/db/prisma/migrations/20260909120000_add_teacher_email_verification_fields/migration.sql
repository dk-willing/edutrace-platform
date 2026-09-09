ALTER TABLE "Teacher"
ADD COLUMN "verificationToken" TEXT,
ADD COLUMN "verificationTokenExpiry" TIMESTAMP(3);