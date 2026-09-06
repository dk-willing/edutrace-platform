import crypto from "node:crypto";
import fs from "node:fs";

const secret = () => crypto.randomBytes(32).toString("hex");
const output = `# Generated locally. Never commit this file or print it in CI.\nNODE_ENV=production\nPORT=5000\nFRONTEND_URL=https://replace-with-your-web-domain\n\n# Fill these from Railway/Render plugins\nDATABASE_URL=\nDIRECT_URL=\nREDIS_URL=\n\nML_SERVICE_URL=http://ml-service:8000\nML_SERVICE_SHARED_SECRET=${secret()}\nML_SERVICE_API_KEY=${secret()}\nEDUTRACE_API_KEY=${secret()}\n\nJWT_ACCESS_SECRET=${secret()}\nJWT_REFRESH_SECRET=${secret()}\nPII_PSEUDONYM_SALT=${secret()}\nJWT_ACCESS_TOKEN_TTL=15m\nJWT_REFRESH_TOKEN_TTL=30d\n\n# Fill these from your transactional email provider\nSMTP_HOST=\nSMTP_PORT=587\nSMTP_USER=\nSMTP_PASSWORD=\nEMAIL_FROM_ADDRESS=no-reply@replace-with-your-domain\n\n# Keep SMS disabled until Arkesel is intentionally configured\nEDUTRACE_SMS_PROVIDER=console\nEDUTRACE_SMS_SENDER_ID=EDUTRACE\nARKESEL_API_KEY=\n`;
fs.writeFileSync(".env.production.generated", output, { mode: 0o600 });
console.log("Wrote .env.production.generated with fresh application secrets.");
console.log(
  "Fill the blank database, Redis, SMTP, and frontend-domain values before deployment.",
);
