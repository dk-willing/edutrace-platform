import { execFileSync } from "node:child_process";
import { cpSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const apiRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const schema = resolve(apiRoot, "../../packages/db/prisma/schema.prisma");
const prismaCommand = process.platform === "win32" ? "prisma.cmd" : "prisma";

execFileSync(prismaCommand, ["generate", `--schema=${schema}`], {
  cwd: apiRoot,
  stdio: "inherit",
});

const generatedSource = resolve(
  apiRoot,
  "../../packages/db/node_modules/.prisma/client",
);
const generatedTarget = resolve(apiRoot, "node_modules/.prisma/client");
mkdirSync(dirname(generatedTarget), { recursive: true });
cpSync(generatedSource, generatedTarget, { recursive: true });
console.log("Prisma Client copied to the API workspace.");
