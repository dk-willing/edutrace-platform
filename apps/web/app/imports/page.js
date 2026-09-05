"use client";

import { useEffect, useState } from "react";
import { Workspace } from "../dashboard/Workspace";
import { apiRequest } from "../lib/api";

export default function ImportsPage() {
  const [classes, setClasses] = useState([]);
  const [uploads, setUploads] = useState([]);
  const [classId, setClassId] = useState("");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  async function load() {
    try {
      const [classResult, uploadResult] = await Promise.all([
        apiRequest("/api/v1/classes"),
        apiRequest("/api/v1/imports"),
      ]);
      setClasses(classResult.classes || []);
      setUploads(uploadResult.uploads || []);
    } catch (requestError) {
      setError(requestError.message);
    }
  }
  useEffect(() => {
    load();
  }, []);
  async function submit(event) {
    event.preventDefault();
    if (!file || !classId) {
      setError("Choose a class and CSV file before uploading.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    const body = new FormData();
    body.append("file", file);
    body.append("classId", classId);
    try {
      const result = await apiRequest("/api/v1/imports", {
        method: "POST",
        body,
      });
      setMessage(
        `Import completed: ${result.upload.rowsAccepted} accepted, ${result.upload.rowsRejected} rejected.`,
      );
      setFile(null);
      event.currentTarget.reset();
      await load();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
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
        <div className="eyebrow">Class CSV import</div>
        <h2 style={{ fontFamily: "Fraunces,serif", margin: "12px 0 8px" }}>
          Add students from a file
        </h2>
        <p className="section-sub">
          Rows are validated before students and observations are stored.
          Invalid rows are reported without pretending they were imported.
        </p>
        <form className="form" onSubmit={submit}>
          <div className="field">
            <label htmlFor="import-class">Class *</label>
            <select
              id="import-class"
              required
              value={classId}
              onChange={(event) => setClassId(event.target.value)}
            >
              <option value="">Choose a class</option>
              {classes.map((classItem) => (
                <option value={classItem.id} key={classItem.id}>
                  {classItem.name} · {classItem.gradeLevel}
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
              onChange={(event) => setFile(event.target.files?.[0] || null)}
            />
          </div>
          <button
            className="button button-primary"
            disabled={busy || !classes.length}
            type="submit"
          >
            {busy ? "Validating and importing..." : "Upload CSV"}
          </button>
        </form>
        {!classes.length && (
          <p className="form-foot">Create a class before uploading students.</p>
        )}
      </section>
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
