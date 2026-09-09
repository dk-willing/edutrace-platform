"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Workspace } from "../../dashboard/Workspace";
import { apiRequest } from "../../lib/api";
import { LoadingButton } from "../../components/LoadingButton";

export default function ClassDetailsPage() {
  const { classId } = useParams();
  const [classRecord, setClassRecord] = useState(null);
  const [students, setStudents] = useState([]);
  const [files, setFiles] = useState([]);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function loadClass() {
    try {
      const result = await apiRequest(`/api/v1/classes/${classId}/students`);
      setClassRecord(result.class);
      setStudents(result.students || []);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (classId) loadClass();
  }, [classId]);

  async function validate(event) {
    event.preventDefault();
    if (!files.length) {
      setError("Choose at least one CSV file before uploading.");
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
      if (!result.valid) {
        setError(
          "Fix the validation errors below and upload the corrected file.",
        );
      }
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
      setMessage(`${result.studentIds.length} students added to this class.`);
      setPreview(null);
      setFiles([]);
      await loadClass();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <Workspace title="Class" subtitle="Loading class roster...">
        <section className="panel">
          <p className="section-sub">Loading students...</p>
        </section>
      </Workspace>
    );
  }

  return (
    <Workspace
      title={classRecord?.name || "Class"}
      subtitle={
        classRecord
          ? `${students.length} student${students.length === 1 ? "" : "s"} · ${classRecord.gradeLevel} · ${classRecord.academicYear}`
          : "Class roster unavailable"
      }
    >
      <Link className="panel-link" href="/classes">
        Back to classes
      </Link>
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
      {!classRecord ? (
        <section className="panel page-card">
          <p className="section-sub">This class could not be found.</p>
        </section>
      ) : (
        <>
          <section className="panel page-card admin-form-panel">
            <div className="panel-head">
              <div>
                <div className="eyebrow">Add students</div>
                <h2>Upload this class roster</h2>
              </div>
              <span className="td-muted">CSV</span>
            </div>
            <p className="section-sub">
              Upload students directly into {classRecord.name}. The class is
              selected automatically, so the roster cannot be assigned to the
              wrong class.
            </p>
            <form className="form" onSubmit={validate}>
              <div className="field">
                <label htmlFor="class-csv-file">Student CSV file</label>
                <input
                  id="class-csv-file"
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
                disabled={busy}
                loading={busy}
                type="submit"
              >
                {busy ? "Validating..." : "Upload and validate"}
              </LoadingButton>
            </form>
          </section>
          {preview && (
            <section className="panel page-card">
              <div className="panel-head">
                <div>
                  <div className="eyebrow">Preview</div>
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
                    {busy ? "Importing..." : "Add students"}
                  </LoadingButton>
                )}
              </div>
              <p className="section-sub">
                {preview.validRows} valid of {preview.totalRows} rows.
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
            </section>
          )}
          <section className="panel page-card">
            <div className="panel-head">
              <h2>Students in {classRecord.name}</h2>
              <span className="td-muted">{students.length} total</span>
            </div>
            {!students.length ? (
              <div className="empty-state compact">
                <h3>No students in this class yet</h3>
                <p>Upload a roster above to add students to this class.</p>
              </div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Student</th>
                      <th>Grade</th>
                      <th>Student ID</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {students.map((student) => (
                      <tr key={student.id}>
                        <td>
                          <strong>
                            {student.identity?.studentName || "Unnamed student"}
                          </strong>
                        </td>
                        <td>{student.gradeLevel}</td>
                        <td className="td-muted">
                          {student.externalId || student.studentKey.slice(0, 8)}
                        </td>
                        <td>
                          <Link
                            className="panel-link"
                            href={`/students/${student.id}`}
                          >
                            View profile ↗
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </Workspace>
  );
}
