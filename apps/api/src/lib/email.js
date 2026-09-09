import { Resend } from "resend";

import { env } from "../config/env.js";
import { logger } from "../utils/logger.js";

const resend = env.RESEND_API_KEY ? new Resend(env.RESEND_API_KEY) : null;

export async function sendVerificationEmail(to, token) {
  if (!resend) return false;

  const verificationUrl = `${env.FRONTEND_URL}/verify-email?token=${encodeURIComponent(token)}`;
  const { error } = await resend.emails.send({
    from: env.EMAIL_FROM_ADDRESS,
    to,
    subject: "Verify your EduTrace account",
    text: `Verify your EduTrace account using this link:\n\n${verificationUrl}\n\nThis link expires in 24 hours.`,
    html: `<p>Verify your EduTrace account using the link below.</p><p><a href="${verificationUrl}">Verify your email address</a></p><p>This link expires in 24 hours.</p>`,
  });
  if (error) {
    logger.error({ err: error, to }, "verification email delivery failed");
    throw new Error("Verification email delivery failed.");
  }
  return true;
}

export async function sendContactChangeEmail({
  to,
  requestedEmail,
  requestedPhone,
  approved = false,
}) {
  if (!resend) return false;
  const subject = approved
    ? "Your EduTrace contact details were updated"
    : "EduTrace contact details change requested";
  const status = approved
    ? "Your school administrator approved the following contact detail change:"
    : "A request was submitted to change your EduTrace contact details. Your current details remain active until your school administrator approves it:";
  const details = [
    requestedEmail ? `Email: ${requestedEmail}` : null,
    requestedPhone ? `Phone: ${requestedPhone}` : null,
  ]
    .filter(Boolean)
    .join("\n");
  const { error } = await resend.emails.send({
    from: env.EMAIL_FROM_ADDRESS,
    to,
    subject,
    text: `${status}\n\n${details}`,
    html: `<p>${status}</p><p>${details.replaceAll("\n", "<br />")}</p>`,
  });
  if (error) {
    logger.error({ err: error, to }, "contact change email delivery failed");
    throw new Error("Contact change email delivery failed.");
  }
  return true;
}
