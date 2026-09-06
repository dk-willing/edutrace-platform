import nodemailer from "nodemailer";

import { env } from "../../config/env.js";

let transporter;

function getTransporter() {
  if (transporter) return transporter;
  if (!env.SMTP_HOST || !env.SMTP_USER || !env.SMTP_PASSWORD) return null;
  transporter = nodemailer.createTransport({
    host: env.SMTP_HOST,
    port: env.SMTP_PORT || 587,
    secure: (env.SMTP_PORT || 587) === 465,
    auth: { user: env.SMTP_USER, pass: env.SMTP_PASSWORD },
  });
  return transporter;
}

export async function sendPasswordResetEmail({ email, resetUrl }) {
  const transport = getTransporter();
  if (!transport) return false;
  await transport.sendMail({
    from: env.EMAIL_FROM_ADDRESS,
    to: email,
    subject: "Reset your EduTrace password",
    text: `Reset your EduTrace password using this link:\n\n${resetUrl}\n\nThis link expires in 30 minutes. If you did not request this, you can ignore this email.`,
  });
  return true;
}
