-- CsvUpload records belong to the class being enrolled or scored.
ALTER TABLE "CsvUpload" ADD COLUMN "classId" TEXT;

-- Preserve existing upload rows where a school has at least one class.
UPDATE "CsvUpload" AS upload
SET "classId" = classes.id
FROM (
  SELECT DISTINCT ON ("schoolId") id, "schoolId"
  FROM "Class"
  ORDER BY "schoolId", "createdAt", id
) AS classes
WHERE upload."schoolId" = classes."schoolId"
  AND upload."classId" IS NULL;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM "CsvUpload" WHERE "classId" IS NULL) THEN
    RAISE EXCEPTION 'Cannot assign existing CSV uploads to a class';
  END IF;
END $$;

ALTER TABLE "CsvUpload" ALTER COLUMN "classId" SET NOT NULL;
CREATE INDEX "CsvUpload_classId_idx" ON "CsvUpload"("classId");
ALTER TABLE "CsvUpload"
  ADD CONSTRAINT "CsvUpload_classId_fkey"
  FOREIGN KEY ("classId") REFERENCES "Class"("id")
  ON DELETE RESTRICT ON UPDATE CASCADE;