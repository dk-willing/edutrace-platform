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
