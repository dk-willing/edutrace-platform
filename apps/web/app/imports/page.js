"use client";

import { useEffect, useState } from "react";
import { Workspace, riskTierLabel } from "../dashboard/Workspace";
import { apiRequest, apiUrl, downloadFile } from "../lib/api";
import { LoadingButton } from "../components/LoadingButton";

export default function ImportsPage() {
  const [classes, setClasses] = useState([]);
  const [uploads, setUploads] = useState([]);
  const [classId, setClassId] = useState("");
  const [files, setFiles] = useState([]);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loadingClasses, setLoadingClasses] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [batchFile, setBatchFile] = useState(null);
  const [batchCapacity, setBatchCapacity] = useState("40");
  const [batchResult, setBatchResult] = useState(null);
  const [scoring, setScoring] = useState(false);
  async function load() {
    setLoadingClasses(true);
    try {
      const [classResult, uploadResult] = await Promise.allSettled([
        apiRequest("/api/v1/classes"),
        apiRequest("/api/v1/imports"),
      ]);
      if (classResult.status === "fulfilled") {
        setClasses(classResult.value.classes || []);
      } else {
        setError(classResult.reason.message);
      }
      if (uploadResult.status === "fulfilled") {
        setUploads(uploadResult.value.uploads || []);
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoadingClasses(false);
    }
  }
  useEffect(() => {
    load();
  }, []);
  async function validate(event) {
    event.preventDefault();
    if (!files.length || !classId) {
      setError("Choose a class and CSV file before uploading.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    const body = new FormData();
    for (const selectedFile of files) body.append("file", selectedFile);
    body.append("classId", classId);
    try {
      const result = await apiRequest("/api/v1/imports", {
        method: "POST",
        body,
      });
      setPreview(result);
      if (!result.valid)
        setError(
          "Fix the validation errors below and upload the corrected file.",
        );
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }
  async function commit() {
    setBusy(true);
    setError("");
    try {
      const result = await apiRequest(
        `/api/v1/imports/${preview.uploadId}/commit`,
        { method: "POST", body: {} },
      );
      setMessage(
        `${result.studentIds.length} students imported successfully. Risk analysis can be retried from the class dashboard.`,
      );
      setPreview(null);
      setFiles([]);
      await load();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }
  async function scoreBatch(event) {
    event.preventDefault();
    if (!batchFile) {
      setError("Choose a model scoring CSV before running analysis.");
      return;
    }
    setScoring(true);
    setError("");
    setBatchResult(null);
    const body = new FormData();
    body.append("file", batchFile);
    try {
      const result = await apiRequest(
        `/api/v1/predictions/batch?capacity=${batchCapacity}`,
        { method: "POST", body },
      );
      setBatchResult(result);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setScoring(false);
    }
  }
  return (
    <Workspace
      title="Imports"
      subtitle="Upload a validated CSV into one of your classes"
    >
      <div className="notice">
        <strong>Before uploading:</strong> choose a class, use the headers in{" "}
        <code>docs/csv-format.md</code>, and never include safeguarding
        disclosures or unnecessary sensitive information.
      </div>
      {error && (
        <div className="notice" role="alert">
          {error}
        </div>
      )}
      {message && (
        <div className="notice admin-notice" role="status">
          {message}
        </div>
      )}
      <section className="panel admin-form-panel">
        <div className="panel-head">
          <div>
            <div className="eyebrow">1. Prepare</div>
            <h2>Download the official template</h2>
          </div>
          <a
            className="button button-outline"
            href={apiUrl("/api/v1/imports/template")}
            download="edutrace-student-template.csv"
          >
            Download CSV Template
          </a>
        </div>
        <p className="section-sub">
          Use percentages from 0 to 100 for attendance, completion, and exam
          scores. Categories and booleans must match the template. Leave
          optional fields blank when information is unavailable.
        </p>
      </section>
      <section className="panel admin-form-panel">
        <div className="eyebrow">2. Validate</div>
        <h2 style={{ fontFamily: "Fraunces,serif", margin: "12px 0 8px" }}>
          Add students from a file
        </h2>
        <p className="section-sub">
          Rows are validated before students and observations are stored.
          Invalid rows are reported without pretending they were imported.
        </p>
        <form className="form" onSubmit={validate}>
          <div className="field">
            <label htmlFor="import-class">Class *</label>
            <select
              id="import-class"
              required
              disabled={loadingClasses || classes.length === 0}
              value={classId}
              onChange={(event) => setClassId(event.target.value)}
            >
              <option value="">
                {loadingClasses ? "Loading your classes..." : "Choose a class"}
              </option>
              {classes.map((classItem) => (
                <option value={classItem.id} key={classItem.id}>
                  {classItem.name} · {classItem.gradeLevel} ·{" "}
                  {classItem.academicYear}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="csv-file">CSV file *</label>
            <input
              id="csv-file"
              required
              type="file"
              accept=".csv,text/csv"
              multiple
              onChange={(event) =>
                setFiles(Array.from(event.target.files || []))
              }
            />
          </div>
          <LoadingButton
            className="button button-primary"
            disabled={busy || !classes.length}
            loading={busy}
            type="submit"
          >
            {busy ? "Validating..." : "Upload and validate"}
          </LoadingButton>
        </form>
        {!loadingClasses && !classes.length && (
          <p className="form-foot">
            No classes are available for your teacher account. Create a class
            first, then return here to import students.
          </p>
        )}
      </section>
      {preview && (
        <section className="panel admin-form-panel">
          <div className="panel-head">
            <div>
              <div className="eyebrow">3. Preview</div>
              <h2>{preview.valid ? "Import ready" : "Changes required"}</h2>
            </div>
            {preview.valid && (
              <LoadingButton
                className="button button-primary"
                disabled={busy}
                loading={busy}
                onClick={commit}
                type="button"
              >
                {busy ? "Importing..." : "Create class records"}
              </LoadingButton>
            )}
          </div>
          <p className="section-sub">
            {preview.validRows} valid of {preview.totalRows} rows.{" "}
            {preview.invalidRows
              ? `${preview.invalidRows} rows need correction.`
              : "All rows are ready for confirmation."}
          </p>
          {preview.errors?.length > 0 && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Row</th>
                    <th>Field</th>
                    <th>Problem</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.errors.map((item, index) => (
                    <tr key={`${item.row}-${item.field}-${index}`}>
                      <td>{item.row || "-"}</td>
                      <td>{item.field}</td>
                      <td>{item.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {preview.valid && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Student</th>
                    <th>ID</th>
                    <th>Grade</th>
                    <th>Term</th>
                    <th>Attendance</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.preview.map((item) => (
                    <tr key={item.externalId || item.studentName}>
                      <td>{item.studentName}</td>
                      <td>{item.externalId || "-"}</td>
                      <td>{item.gradeLevel}</td>
                      <td>T1</td>
                      <td>{item.attendanceRateTermToDate ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
      <section className="panel admin-form-panel">
        <div className="eyebrow">4. Risk analysis</div>
        <h2>Score a model CSV</h2>
        <p className="section-sub">
          Upload the model scoring template with <code>student_key</code>,
          <code> school_id</code>, <code>grade_level</code>, term, week, and raw
          student indicators. EduTrace will return a capacity-ranked worklist.
        </p>
        <form className="form" onSubmit={scoreBatch}>
          <div className="field">
            <label htmlFor="batch-csv-file">Model scoring CSV *</label>
            <input
              id="batch-csv-file"
              required
              type="file"
              accept=".csv,text/csv"
              onChange={(event) =>
                setBatchFile(event.target.files?.[0] || null)
              }
            />
          </div>
          <div className="field">
            <label htmlFor="batch-capacity">Follow-up capacity</label>
            <input
              id="batch-capacity"
              min="1"
              max="500"
              type="number"
              value={batchCapacity}
              onChange={(event) => setBatchCapacity(event.target.value)}
            />
          </div>
          <LoadingButton
            className="button button-primary"
            disabled={scoring}
            loading={scoring}
            type="submit"
          >
            {scoring ? "Analyzing..." : "Run risk analysis"}
          </LoadingButton>
        </form>
      </section>
      {batchResult?.summary && (
        <section className="panel page-card">
          <div className="panel-head">
            <div>
              <div className="eyebrow">Analysis results</div>
              <h2>Risk worklist</h2>
            </div>
            <span className="td-muted">
              {batchResult.summary.rows_scored} scored
            </span>
          </div>
          <div className="stat-grid">
            {Object.entries(batchResult.summary.tier_counts || {}).map(
              ([tier, count]) => (
                <div className="stat" key={tier}>
                  <div className="stat-label">{riskTierLabel(tier)}</div>
                  <div className="stat-value">{count}</div>
                </div>
              ),
            )}
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Student key</th>
                  <th>Risk</th>
                  <th>Tier</th>
                  <th>Indicators</th>
                </tr>
              </thead>
              <tbody>
                {(batchResult.worklist || []).map((item) => (
                  <tr key={item.observation_id}>
                    <td>{item.student_key}</td>
                    <td>{(item.risk * 100).toFixed(1)}%</td>
                    <td>
                      <span
                        className={`badge badge-${String(item.tier).toLowerCase()}`}
                      >
                        {riskTierLabel(item.tier)}
                      </span>
                    </td>
                    <td>
                      {item.drivers
                        ?.slice(0, 2)
                        .map((driver) => driver.label)
                        .join(", ") || "No ranked indicators"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {batchResult.guidance && (
            <p className="form-foot">{batchResult.guidance}</p>
          )}
          {batchResult.staffAlert?.attempted && (
            <p className="form-foot" role="status">
              {batchResult.staffAlert.accepted
                ? "Urgent-support alert sent to your registered phone."
                : "Urgent-support students found, but the teacher SMS could not be delivered."}
            </p>
          )}
          {batchResult.reportId && (
            <p className="form-foot">
              <button
                className="panel-link"
                onClick={() =>
                  downloadFile(
                    `/api/v1/reports/analysis/${batchResult.reportId}/download`,
                    `edutrace-report-${batchResult.reportId}.pdf`,
                  )
                }
                type="button"
              >
                Download this analysis as PDF
              </button>
            </p>
          )}
        </section>
      )}
      <section className="panel page-card">
        <div className="panel-head">
          <h2>Import history</h2>
          <span className="td-muted">
            {uploads.length} upload{uploads.length === 1 ? "" : "s"}
          </span>
        </div>
        {!uploads.length ? (
          <div className="empty-state compact">
            <h3>No imports yet</h3>
            <p>Your completed and failed uploads will appear here.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>File</th>
                  <th>Class</th>
                  <th>Rows</th>
                  <th>Status</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {uploads.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.originalFilename}</strong>
                    </td>
                    <td>{item.class?.name}</td>
                    <td>
                      {item.rowsAccepted || 0}/{item.rowsTotal || 0}
                    </td>
                    <td>
                      <span
                        className={`badge ${item.status === "COMPLETED" ? "badge-low" : item.status === "FAILED" ? "badge-high" : "badge-watch"}`}
                      >
                        {item.status}
                      </span>
                    </td>
                    <td className="td-muted">
                      {new Date(item.createdAt).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </Workspace>
  );
}
