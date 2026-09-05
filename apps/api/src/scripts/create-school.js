import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import { resolve, dirname } from "node:path";
import argon2 from "argon2";
import { PrismaClient } from "@prisma/client";
import dotenv from "dotenv";

dotenv.config({
  path: resolve(dirname(fileURLToPath(import.meta.url)), "../../../../.env"),
});

const prisma = new PrismaClient();

function argument(name, fallback = undefined) {
  const prefix = `--${name}=`;
  const value = process.argv.find((item) => item.startsWith(prefix));
  return value ? value.slice(prefix.length).trim() : fallback;
}

function required(name, fallback = undefined) {
  const value = argument(name, fallback);
  if (!value) throw new Error(`Missing --${name}`);
  return value;
}

function printUsage() {
  console.log(`Usage:
  npm run create:school --workspace=@edutrace/api -- --name="ABC Junior High" --code=ABC-JHS --district=Accra --region=Greater-Accra --admin-email=admin@example.com --admin-password="change-this-password"

The command creates one ACTIVE school and one ACTIVE SYSTEM_ADMIN account for local development.
`);
}

async function main() {
  if (process.argv.includes("--help")) {
    printUsage();
    return;
  }

  const name = required("name");
  const schoolCode = required("code").toUpperCase();
  const district = required("district");
  const region = required("region");
  const adminEmail = required("admin-email").toLowerCase();
  const adminPassword = required("admin-password");
  if (adminPassword.length < 12)
    throw new Error("--admin-password must be at least 12 characters");

  const existingSchool = await prisma.school.findUnique({
    where: { schoolCode },
  });
  if (existingSchool)
    throw new Error(`School code ${schoolCode} already exists`);
  const existingAdmin = await prisma.teacher.findUnique({
    where: { email: adminEmail },
  });
  if (existingAdmin)
    throw new Error(`Admin email ${adminEmail} already exists`);

  const passwordHash = await argon2.hash(adminPassword);
  const result = await prisma.$transaction(async (tx) => {
    const school = await tx.school.create({
      data: { name, schoolCode, district, region, status: "ACTIVE" },
    });
    const admin = await tx.teacher.create({
      data: {
        schoolId: null,
        firstName: "System",
        lastName: "Administrator",
        email: adminEmail,
        passwordHash,
        role: "SYSTEM_ADMIN",
        status: "ACTIVE",
        emailVerified: true,
        approvedAt: new Date(),
      },
    });
    await tx.school.update({
      where: { id: school.id },
      data: { onboardedByAdminId: admin.id },
    });
    await tx.auditLog.create({
      data: {
        schoolId: school.id,
        actorId: admin.id,
        event: "SCHOOL_CREATED",
        payload: { schoolCode, source: "development_bootstrap" },
      },
    });
    return { school, admin };
  });

  console.log(`School created successfully.`);
  console.log(`School code: ${result.school.schoolCode}`);
  console.log(`School ID: ${result.school.id}`);
  console.log(`System admin: ${result.admin.email}`);
  console.log("Teachers can now register using the school code above.");
}

main()
  .catch((error) => {
    console.error(`Could not create school: ${error.message}`);
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
