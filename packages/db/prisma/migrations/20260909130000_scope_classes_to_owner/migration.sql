DROP INDEX "Class_schoolId_name_academicYear_key";
CREATE UNIQUE INDEX "Class_schoolId_ownerId_name_academicYear_key" ON "Class"("schoolId", "ownerId", "name", "academicYear");