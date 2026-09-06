import crypto from "node:crypto";

import { env } from "../../config/env.js";

export async function sendUrgentStaffAlert({
  teacherMsisdn,
  schoolName,
  urgentCount,
  schoolId,
  teacherId,
}) {
  if (!urgentCount)
    return { attempted: false, accepted: false, reason: "no urgent students" };
  if (!teacherMsisdn)
    return {
      attempted: false,
      accepted: false,
      reason: "teacher has no mobile number",
    };
  const target = `${env.ML_SERVICE_URL}/internal/v1/notify/staff`;
  const body = JSON.stringify({
    teacher_msisdn: teacherMsisdn,
    school_name: schoolName || "your school",
    urgent_count: urgentCount,
  });
  const timestamp = String(Date.now());
  const message = `edutrace-api.${timestamp}.${body}`;
  const signature = crypto
    .createHmac("sha256", env.ML_SERVICE_SHARED_SECRET)
    .update(message)
    .digest("hex");
  const response = await fetch(target, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": env.ML_SERVICE_API_KEY,
      "X-Service-Id": "edutrace-api",
      "X-Service-Timestamp": timestamp,
      "X-Service-Signature": signature,
    },
    body,
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.detail || "Teacher alert failed.");
  return { attempted: true, ...result };
}
