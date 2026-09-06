"use client";

import { useEffect, useState } from "react";
import { Workspace } from "../dashboard/Workspace";
import { apiRequest } from "../lib/api";

const initialPassword = {
  currentPassword: "",
  password: "",
  passwordConfirmation: "",
};

export default function SettingsPage() {
  const [teacher, setTeacher] = useState(null);
  const [passwordForm, setPasswordForm] = useState(initialPassword);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    apiRequest("/api/v1/auth/me")
      .then((result) => setTeacher(result.teacher))
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);

  async function changePassword(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const result = await apiRequest("/api/v1/auth/change-password", {
        method: "POST",
        body: passwordForm,
      });
      setMessage(`${result.message} Sign in again with your new password.`);
      setPasswordForm(initialPassword);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Workspace title="Settings" subtitle="Your account and school workspace">
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
      <section className="panel">
        <div className="panel-head">
          <h2>Account</h2>
        </div>
        {loading ? (
          <p className="section-sub">Loading account details...</p>
        ) : (
          teacher && (
            <div className="form">
              <div className="field">
                <label htmlFor="name">Name</label>
                <input
                  id="name"
                  value={`${teacher.firstName} ${teacher.lastName}`}
                  readOnly
                />
              </div>
              <div className="field">
                <label htmlFor="email">Verified email</label>
                <input id="email" value={teacher.email} readOnly />
              </div>
              <div className="field">
                <label htmlFor="phone">Mobile number</label>
                <input
                  id="phone"
                  value={teacher.phone || "Not provided"}
                  readOnly
                />
              </div>
              <div className="field">
                <label htmlFor="school">School</label>
                <input
                  id="school"
                  value={
                    teacher.school
                      ? `${teacher.school.name} · ${teacher.school.schoolCode}`
                      : "Not assigned"
                  }
                  readOnly
                />
              </div>
              <div className="field">
                <label htmlFor="role">Role</label>
                <input id="role" value={teacher.role} readOnly />
              </div>
            </div>
          )
        )}
      </section>
      <section className="panel page-card">
        <div className="panel-head">
          <h2>Change password</h2>
        </div>
        <p className="section-sub">
          Use your current password to set a new one. Other refresh sessions
          will be signed out after the change.
        </p>
        <form className="form" onSubmit={changePassword}>
          <div className="field">
            <label htmlFor="current-password">Current password</label>
            <input
              id="current-password"
              required
              type="password"
              value={passwordForm.currentPassword}
              onChange={(event) =>
                setPasswordForm({
                  ...passwordForm,
                  currentPassword: event.target.value,
                })
              }
              autoComplete="current-password"
            />
          </div>
          <div className="field">
            <label htmlFor="new-password">New password</label>
            <input
              id="new-password"
              required
              minLength={12}
              type="password"
              value={passwordForm.password}
              onChange={(event) =>
                setPasswordForm({
                  ...passwordForm,
                  password: event.target.value,
                })
              }
              autoComplete="new-password"
            />
          </div>
          <div className="field">
            <label htmlFor="confirm-password">Confirm new password</label>
            <input
              id="confirm-password"
              required
              minLength={12}
              type="password"
              value={passwordForm.passwordConfirmation}
              onChange={(event) =>
                setPasswordForm({
                  ...passwordForm,
                  passwordConfirmation: event.target.value,
                })
              }
              autoComplete="new-password"
            />
          </div>
          <button
            className="button button-primary"
            disabled={saving}
            type="submit"
          >
            {saving ? "Updating..." : "Update password"}
          </button>
        </form>
      </section>
      <section className="panel page-card">
        <div className="panel-head">
          <h2>Privacy controls</h2>
        </div>
        <p className="section-sub">
          Your access is determined by your verified school account. Sensitive
          safeguarding disclosures are never shown in student timelines or sent
          to the model.
        </p>
      </section>
    </Workspace>
  );
}
