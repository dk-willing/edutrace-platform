"use client";

import { useEffect, useState } from "react";

import { Workspace } from "../dashboard/Workspace";
import {
  apiRequest,
  clearAccessToken,
  getAccessToken,
  getCurrentTeacher,
  setAccessToken,
  setCurrentTeacher,
} from "../lib/api";

const emptyForm = {
  name: "",
  schoolCode: "",
  district: "",
  region: "",
  address: "",
  contactEmail: "",
  contactPhone: "",
};

function codeFromName(name) {
  return name
    .replace(/[^a-zA-Z0-9 ]/g, "")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 4)
    .map((word) => word.slice(0, 3))
    .join("-")
    .toUpperCase();
}

export default function AdminPage() {
  const [form, setForm] = useState(emptyForm);
  const [schools, setSchools] = useState([]);
  const [teachers, setTeachers] = useState([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [admin, setAdmin] = useState(null);
  const [authBusy, setAuthBusy] = useState(false);
  const [authForm, setAuthForm] = useState({ email: "", password: "" });

  async function loadSchools() {
    try {
      const result = await apiRequest("/api/v1/admin/schools");
      setSchools(result.schools || []);
      setError("");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadTeachers() {
    try {
      const result = await apiRequest("/api/v1/admin/teachers");
      setTeachers(result.teachers || []);
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  useEffect(() => {
    const storedTeacher = getCurrentTeacher();
    if (storedTeacher?.role === "SYSTEM_ADMIN") setAdmin(storedTeacher);
    if (getAccessToken() && storedTeacher?.role === "SYSTEM_ADMIN") {
      loadSchools();
      loadTeachers();
    } else setLoading(false);
  }, []);

  async function signIn(event) {
    event.preventDefault();
    setAuthBusy(true);
    setError("");
    try {
      const result = await apiRequest("/api/v1/auth/login", {
        method: "POST",
        body: authForm,
      });
      if (result.teacher?.role !== "SYSTEM_ADMIN") {
        clearAccessToken();
        throw new Error("This account is not a system administrator.");
      }
      setAccessToken(result.accessToken);
      setCurrentTeacher(result.teacher);
      setAdmin(result.teacher);
      setLoading(true);
      await loadSchools();
      await loadTeachers();
    } catch (requestError) {
      clearAccessToken();
      setError(requestError.message);
    } finally {
      setAuthBusy(false);
    }
  }

  function signOut() {
    clearAccessToken();
    setAdmin(null);
    setSchools([]);
    setMessage("");
  }

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
    if (field === "name" && !form.schoolCode) {
      setForm((current) => ({
        ...current,
        name: value,
        schoolCode: codeFromName(value),
      }));
    }
  }

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const result = await apiRequest("/api/v1/admin/schools", {
        method: "POST",
        body: form,
      });
      setMessage(
        `School created. Registration code: ${result.school.schoolCode}`,
      );
      setForm(emptyForm);
      await loadSchools();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function approveTeacher(teacherId) {
    setError("");
    setMessage("");
    try {
      await apiRequest(`/api/v1/admin/teachers/${teacherId}/approve`, {
        method: "POST",
      });
      setMessage("Teacher account approved successfully.");
      await loadTeachers();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  if (!getAccessToken() || !admin) {
    return (
      <div className="auth-page admin-auth-page">
        <div className="auth-panel">
          <div className="logo">
            <span className="logo-mark">ET</span>EduTrace
          </div>
          <div>
            <div className="auth-kicker">System administration</div>
            <p className="auth-aside">
              A calm control room for the school directory.
            </p>
            <p className="auth-note">
              Sign in with a verified system administrator account to create
              schools and assign registration codes.
            </p>
          </div>
          <p className="auth-note">
            The first system administrator must be bootstrapped securely from
            the API command line.
          </p>
        </div>
        <div className="auth-panel">
          <div className="form-wrap">
            <div className="eyebrow">Admin sign in</div>
            <h1>Open administration</h1>
            <p className="form-intro">
              Your role is checked by the backend before any school data is
              returned.
            </p>
            {error && (
              <div className="notice" role="alert">
                {error}
              </div>
            )}
            <form className="form" onSubmit={signIn}>
              <div className="field">
                <label htmlFor="admin-email">Email address</label>
                <input
                  id="admin-email"
                  required
                  type="email"
                  value={authForm.email}
                  onChange={(event) =>
                    setAuthForm({ ...authForm, email: event.target.value })
                  }
                  placeholder="admin@example.com"
                />
              </div>
              <div className="field">
                <label htmlFor="admin-password">Password</label>
                <input
                  id="admin-password"
                  required
                  minLength={12}
                  type="password"
                  value={authForm.password}
                  onChange={(event) =>
                    setAuthForm({ ...authForm, password: event.target.value })
                  }
                  placeholder="Your administrator password"
                />
              </div>
              <button
                className="button button-primary"
                disabled={authBusy}
                type="submit"
              >
                {authBusy ? "Checking account..." : "Sign in to admin"}
              </button>
            </form>
            <p className="form-foot">
              The initial account is created with{" "}
              <code>npm run create:school</code>.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <Workspace
      title="School administration"
      subtitle="Create schools and assign the registration codes teachers will use."
    >
      <div className="admin-hero">
        <div>
          <div className="eyebrow">System administration</div>
          <h2>Build the school directory.</h2>
          <p>
            Give every school a clear identity before teachers and learners
            enter the platform.
          </p>
        </div>
        <div className="admin-hero-actions">
          <span className="admin-identity">{admin.email}</span>
          <button
            className="button button-outline admin-signout"
            type="button"
            onClick={signOut}
          >
            Sign out
          </button>
          <div className="admin-hero-mark">+</div>
        </div>
      </div>
      <div className="notice admin-notice">
        <strong>Administrator access required.</strong> Only a signed-in{" "}
        <code>SYSTEM_ADMIN</code> can create schools. School creation is
        recorded in the audit log.
      </div>
      {error && (
        <div className="notice" role="alert">
          {error}
        </div>
      )}
      {message && (
        <div className="notice" role="status">
          {message}
        </div>
      )}
      <div className="grid-2">
        <section className="panel admin-form-panel">
          <div className="panel-head">
            <h2>Create a school</h2>
            <span className="td-muted">Required fields marked *</span>
          </div>
          <form className="form" onSubmit={submit}>
            <div className="field">
              <label htmlFor="school-name">School name *</label>
              <input
                id="school-name"
                required
                value={form.name}
                onChange={(event) => updateField("name", event.target.value)}
                placeholder="ABC Junior High"
              />
            </div>
            <div className="field">
              <label htmlFor="school-code">School code *</label>
              <input
                id="school-code"
                className="admin-code-input"
                required
                pattern="[A-Za-z0-9-]+"
                value={form.schoolCode}
                onChange={(event) =>
                  updateField("schoolCode", event.target.value.toUpperCase())
                }
                placeholder="ABC-JHS"
              />
              <span className="td-muted">
                Teachers enter this code during registration. Use letters,
                numbers, and hyphens.
              </span>
            </div>
            <div
              className="feature-grid"
              style={{ gridTemplateColumns: "1fr 1fr", gap: 10 }}
            >
              <div className="field">
                <label htmlFor="district">District *</label>
                <input
                  id="district"
                  required
                  value={form.district}
                  onChange={(event) =>
                    updateField("district", event.target.value)
                  }
                  placeholder="Accra"
                />
              </div>
              <div className="field">
                <label htmlFor="region">Region *</label>
                <input
                  id="region"
                  required
                  value={form.region}
                  onChange={(event) =>
                    updateField("region", event.target.value)
                  }
                  placeholder="Greater Accra"
                />
              </div>
            </div>
            <div className="field">
              <label htmlFor="address">Address</label>
              <input
                id="address"
                value={form.address}
                onChange={(event) => updateField("address", event.target.value)}
                placeholder="Optional school address"
              />
            </div>
            <div
              className="feature-grid"
              style={{ gridTemplateColumns: "1fr 1fr", gap: 10 }}
            >
              <div className="field">
                <label htmlFor="contact-email">Contact email</label>
                <input
                  id="contact-email"
                  type="email"
                  value={form.contactEmail}
                  onChange={(event) =>
                    updateField("contactEmail", event.target.value)
                  }
                  placeholder="office@school.edu.gh"
                />
              </div>
              <div className="field">
                <label htmlFor="contact-phone">Contact phone</label>
                <input
                  id="contact-phone"
                  value={form.contactPhone}
                  onChange={(event) =>
                    updateField("contactPhone", event.target.value)
                  }
                  placeholder="Optional"
                />
              </div>
            </div>
            <button
              className="button button-primary"
              disabled={saving}
              type="submit"
            >
              {saving ? "Creating school..." : "Create school"}
            </button>
          </form>
        </section>
        <section className="panel">
          <div className="panel-head">
            <h2>Registration flow</h2>
          </div>
          <div className="task">
            <span className="task-dot" />
            <div>
              <p>1. Create the school here</p>
              <small>
                The API assigns an active school record and audit event.
              </small>
            </div>
          </div>
          <div className="task">
            <span className="task-dot" style={{ background: "var(--gold)" }} />
            <div>
              <p>2. Share the school code</p>
              <small>Teachers use it at the registration page.</small>
            </div>
          </div>
          <div className="task">
            <span className="task-dot" style={{ background: "var(--teal)" }} />
            <div>
              <p>3. Approve verified teachers</p>
              <small>Review pending accounts before they can sign in.</small>
            </div>
          </div>
        </section>
      </div>
      <section className="panel page-card admin-table-panel">
        <div className="panel-head">
          <h2>Schools</h2>
          <span className="td-muted">
            {loading
              ? "Loading..."
              : `${schools.length} school${schools.length === 1 ? "" : "s"}`}
          </span>
        </div>
        {!loading && schools.length === 0 ? (
          <p className="section-sub">No schools have been created yet.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>School</th>
                  <th>Code</th>
                  <th>Location</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {schools.map((school) => (
                  <tr key={school.id}>
                    <td>
                      <strong>{school.name}</strong>
                    </td>
                    <td>
                      <strong>{school.schoolCode}</strong>
                    </td>
                    <td className="td-muted">
                      {school.district}, {school.region}
                    </td>
                    <td>
                      <span className="badge badge-low">{school.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="panel page-card admin-table-panel">
        <div className="panel-head">
          <h2>Teacher approvals</h2>
          <span className="td-muted">
            {
              teachers.filter(
                (teacher) => teacher.status === "PENDING_SCHOOL_APPROVAL",
              ).length
            }{" "}
            pending
          </span>
        </div>
        {teachers.length === 0 ? (
          <p className="section-sub">No teacher accounts found.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Teacher</th>
                  <th>Email</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {teachers.map((teacher) => (
                  <tr key={teacher.id}>
                    <td>
                      <strong>
                        {teacher.firstName} {teacher.lastName}
                      </strong>
                    </td>
                    <td className="td-muted">{teacher.email}</td>
                    <td>
                      <span
                        className={`badge ${teacher.status === "ACTIVE" ? "badge-low" : "badge-watch"}`}
                      >
                        {teacher.status.replaceAll("_", " ")}
                      </span>
                    </td>
                    <td>
                      {teacher.status === "PENDING_SCHOOL_APPROVAL" ? (
                        <button
                          className="button button-primary"
                          type="button"
                          onClick={() => approveTeacher(teacher.id)}
                        >
                          Approve
                        </button>
                      ) : (
                        <span className="td-muted">Approved</span>
                      )}
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
