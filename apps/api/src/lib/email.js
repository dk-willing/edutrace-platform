import { Resend } from "resend";

import { env } from "../config/env.js";

const resend = env.RESEND_API_KEY ? new Resend(env.RESEND_API_KEY) : null;

export async function sendVerificationEmail(to, token) {
  if (!resend) return false;

  const verificationUrl = `${env.FRONTEND_URL}/verify-email?token=${encodeURIComponent(token)}`;
  await resend.emails.send({
    from: env.EMAIL_FROM_ADDRESS,
    to,
    subject: "Verify your EduTrace account",
    text: `Verify your EduTrace account using this link:\n\n${verificationUrl}\n\nThis link expires in 24 hours.`,
    html: `<p>Verify your EduTrace account using the link below.</p><p><a href="${verificationUrl}">Verify your email address</a></p><p>This link expires in 24 hours.</p>`,
  });
  return true;
}
