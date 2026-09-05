# Student CSV format

Choose a class before importing. The first row must contain headers. Required
identity columns are `studentName` and `gradeLevel`; `externalId` is strongly
recommended for future updates and duplicate detection.

Example:

```csv
studentName,externalId,gradeLevel,guardianName,guardianMsisdn,attendanceRateTermToDate,attendanceRateLast4w,avgExamScore,assessmentCompletionRate,coreSubjectFailures,feeStatus,hasTextbooks,hasUniform,doesPaidOrFarmWork,distanceBand
Amina Mensah,STU-2041,JHS2,Kofi Mensah,233240000001,0.88,0.79,71.5,0.92,0,PAID,true,true,false,NEAR
Kojo Owusu,STU-2057,JHS2,Adwoa Owusu,233240000002,0.64,0.52,58.0,0.67,2,ARREARS,true,false,true,FAR
Abena Boateng,STU-2018,JHS2,Yaw Boateng,233240000003,0.94,0.93,76.0,0.96,0,PAID,true,true,false,NEAR
```

Attendance and completion rates must be decimals from `0` to `1` or be mapped
through the import preview. Scores must use the school-approved scale. Boolean
values should be `true` or `false`. Do not include safeguarding disclosures,
free-text narratives, or unnecessary medical information in the CSV.

The import workflow will validate headers, values, duplicates, and row errors
before writing students or observations. Never upload real data into the demo
environment.
