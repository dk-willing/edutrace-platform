import { prisma } from "../../db/prisma.js";

const ALLOWED_TIERS = new Set(["LOW", "WATCH", "ELEVATED", "HIGH"]);

export function normalizeWorklist(worklist) {
  return (worklist || []).map((item) => {
    const tier = String(item.tier || "").toUpperCase();
    if (!ALLOWED_TIERS.has(tier)) {
      throw new Error(`ML service returned unsupported risk tier: ${tier}`);
    }
    return { ...item, tier };
  });
}

export async function createAnalysisReport({
  schoolId,
  generatedById,
  source,
  filename,
  summary,
  worklist,
}) {
  const results = normalizeWorklist(worklist);
  const tierCounts = Object.fromEntries(
    ["LOW", "WATCH", "ELEVATED", "HIGH"].map((tier) => [
      tier,
      results.filter((item) => item.tier === tier).length,
    ]),
  );
  return prisma.analysisReport.create({
    data: {
      schoolId,
      generatedById,
      source,
      filename: filename || null,
      modelVersion: summary?.model_version || null,
      totalRows: summary?.rows_in ?? results.length,
      rowsScored: summary?.rows_scored ?? results.length,
      highCount: tierCounts.HIGH,
      tierCounts,
      results,
    },
  });
}

function escapePdfText(value) {
  return String(value)
    .replaceAll("\\", "\\\\")
    .replaceAll("(", "\\(")
    .replaceAll(")", "\\)");
}

export function reportPdf(report) {
  const counts = report.tierCounts || {};
  const lines = [
    "EduTrace Risk Analysis Report",
    `Generated: ${new Date(report.createdAt).toISOString()}`,
    `Source: ${report.source}${report.filename ? ` (${report.filename})` : ""}`,
    `Model: ${report.modelVersion || "Unavailable"}`,
    `Rows scored: ${report.rowsScored}/${report.totalRows}`,
    `LOW: ${counts.LOW || 0}   WATCH: ${counts.WATCH || 0}   ELEVATED: ${counts.ELEVATED || 0}   HIGH: ${counts.HIGH || 0}`,
    "",
    "Student key | Risk | Tier",
    ...(report.results || []).map(
      (item) =>
        `${item.student_key} | ${(Number(item.risk || 0) * 100).toFixed(1)}% | ${item.tier}`,
    ),
  ];
  const content = [
    "BT",
    "/F1 10 Tf",
    "50 760 Td",
    ...lines.flatMap((line, index) => [
      index ? "0 -16 Td" : "",
      `(${escapePdfText(line)}) Tj`,
    ]),
    "ET",
  ]
    .filter(Boolean)
    .join("\n");
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
    `<< /Length ${Buffer.byteLength(content) + 1} >>\nstream\n${content}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((object, index) => {
    offsets[index + 1] = Buffer.byteLength(pdf);
    pdf += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xref = Buffer.byteLength(pdf);
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n${offsets
    .slice(1)
    .map((offset) => `${String(offset).padStart(10, "0")} 00000 n `)
    .join(
      "\n",
    )}\ntrailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return Buffer.from(pdf, "binary");
}
