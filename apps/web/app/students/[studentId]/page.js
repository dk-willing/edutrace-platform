"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Workspace, RiskBadge } from "../../dashboard/Workspace";
import { apiRequest } from "../../lib/api";
import { LoadingButton } from "../../components/LoadingButton";

export default function StudentProfilePage() {
  const { studentId } = useParams();
  const router = useRouter();
  const [student, setStudent] = useState(null);
  const [classes, setClasses] = useState([]);
  const [assessment, setAssessment] = useState(null);
  const [form, setForm] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [reviewing, setReviewing] = useState(false);

  useEffect(() => {
    if (!studentId) return;
    Promise.all([
      apiRequest(`/api/v1/students/${studentId}`),
      apiRequest("/api/v1/classes"),
    ])
      .then(([studentResult, classResult]) => {
        const record = studentResult.student;
        setStudent(record);
        setAssessment(studentResult.latestAssessment);
        setClasses(classResult.classes || []);
        setForm({
          studentName: record.identity?.studentName || "",
          externalId: record.externalId || "",
          guardianName: record.identity?.guardianName || "",
          guardianMsisdn: record.identity?.guardianMsisdn || "",
          gradeLevel: record.gradeLevel,
          classId: record.classId || "",
        });
      })
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, [studentId]);

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function save(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const result = await apiRequest(`/api/v1/students/${studentId}`, {
        method: "PATCH",
        body: {
          ...form,
          externalId: form.externalId || null,
          guardianName: form.guardianName || null,
          guardianMsisdn: form.guardianMsisdn || null,
          classId: form.classId || null,
        },
      });
      setStudent(result.student);
      setMessage("Student profile updated.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function removeStudent() {
    if (
      !window.confirm(
        "Remove this student from the active roster? Historical records will be retained.",
      )
    )
      return;
    setDeleting(true);
    setError("");
    try {
      await apiRequest(`/api/v1/students/${studentId}`, { method: "DELETE" });
      router.push("/students");
    } catch (requestError) {
      setError(requestError.message);
      setDeleting(false);
    }
  }

  async function review(decision) {
    setReviewing(true);
    setError("");
    setMessage("");
    try {
      const result = await apiRequest(
        `/api/v1/students/${studentId}/assessment/review`,
        { method: "POST", body: { decision } },
      );
      setAssessment((current) => ({
        ...current,
        reviewOutcome: result.reviewOutcome,
      }));
      setMessage(`Assessment marked ${decision.toLowerCase()}.`);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setReviewing(false);
    }
  }

  if (loading) {
    return (
      <Workspace title="Student profile" subtitle="Loading student record...">
        <section className="panel">
          <p className="section-sub">Loading...</p>
        </section>
      </Workspace>
    );
  }
  if (!student || !form) {
    return (
      <Workspace title="Student profile" subtitle="Student record unavailable">
        <div className="notice" role="alert">
          {error || "Student not found."}
        </div>
        <Link className="button button-outline" href="/students">
          Back to students
        </Link>
      </Workspace>
    );
  }

  return (
    <Workspace
      title={student.identity?.studentName || "Student profile"}
      subtitle={`${student.externalId || student.studentKey.slice(0, 8)} · ${student.class?.name || "Unassigned"}`}
    >
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
      <div className="grid-2">
        <section className="panel">
          <div className="panel-head">
            <h2>Edit student</h2>
            <span className="td-muted">Active roster</span>
          </div>
          <form className="form" onSubmit={save}>
            <div className="field">
              <label htmlFor="student-name">Student name</label>
              <input
                id="student-name"
                value={form.studentName}
                onChange={(event) => update("studentName", event.target.value)}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="external-id">External ID</label>
              <input
                id="external-id"
                value={form.externalId}
                onChange={(event) => update("externalId", event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="guardian-name">Guardian name</label>
              <input
                id="guardian-name"
                value={form.guardianName}
                onChange={(event) => update("guardianName", event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="guardian-phone">Guardian phone</label>
              <input
                id="guardian-phone"
                value={form.guardianMsisdn}
                onChange={(event) =>
                  update("guardianMsisdn", event.target.value)
                }
              />
            </div>
            <div className="field">
              <label htmlFor="student-grade">Grade</label>
              <select
                id="student-grade"
                value={form.gradeLevel}
                onChange={(event) => update("gradeLevel", event.target.value)}
              >
                <option value="JHS1">JHS 1</option>
                <option value="JHS2">JHS 2</option>
                <option value="JHS3">JHS 3</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="student-class">Class</label>
              <select
                id="student-class"
                value={form.classId}
                onChange={(event) => update("classId", event.target.value)}
              >
                <option value="">Unassigned</option>
                {classes.map((classItem) => (
                  <option key={classItem.id} value={classItem.id}>
                    {classItem.name} · {classItem.gradeLevel}
                  </option>
                ))}
              </select>
            </div>
            <LoadingButton
              className="button button-primary"
              disabled={saving}
              loading={saving}
              type="submit"
            >
              {saving ? "Saving..." : "Save changes"}
            </LoadingButton>
          </form>
        </section>
        <section className="panel">
          <div className="panel-head">
            <h2>Risk status</h2>
            {assessment && <RiskBadge>{assessment.tier}</RiskBadge>}
          </div>
          {assessment ? (
            <>
              <div className="stat-value">
                {(assessment.risk * 100).toFixed(1)}%
              </div>
              <p className="section-sub">
                Latest model assessment. Human review is required before action.
              </p>
              <p className="form-foot">
                Model {assessment.modelRegistration?.modelVersion || "unknown"}{" "}
                · {new Date(assessment.scoredAt).toLocaleString()}
              </p>
              <p>
                <strong>
                  {assessment.reviewOutcome
                    ? `Reviewed: ${assessment.reviewOutcome.decision}`
                    : "Waiting for teacher review"}
                </strong>
              </p>
              <div className="button-row">
                <LoadingButton
                  className="button button-primary"
                  disabled={reviewing}
                  loading={reviewing}
                  onClick={() => review("CONFIRM")}
                  type="button"
                >
                  Confirm and approve
                </LoadingButton>
                <button
                  className="button button-outline"
                  disabled={reviewing}
                  onClick={() => review("DEFER")}
                  type="button"
                >
                  Defer review
                </button>
              </div>
            </>
          ) : (
            <p className="section-sub">
              No risk assessment is available for this student.
            </p>
          )}
          <button
            className="button button-outline"
            disabled={deleting}
            onClick={removeStudent}
            type="button"
          >
            {deleting ? "Removing..." : "Remove from active roster"}
          </button>
        </section>
      </div>
      <p className="form-foot">
        <Link href="/students">Back to students</Link>
      </p>
    </Workspace>
  );
}
