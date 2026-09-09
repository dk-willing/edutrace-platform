"use client";

import { useEffect, useState } from "react";
import { Workspace } from "../dashboard/Workspace";
import { apiRequest } from "../lib/api";
import { LoadingButton } from "../components/LoadingButton";

const initialPassword = {
  currentPassword: "",
  password: "",
  passwordConfirmation: "",
};
const initialContact = { email: "", phone: "" };

export default function SettingsPage() {
  const [teacher, setTeacher] = useState(null);
  const [passwordForm, setPasswordForm] = useState(initialPassword);
  const [contactForm, setContactForm] = useState(initialContact);
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

  async function requestContactChange(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const result = await apiRequest("/api/v1/auth/contact-change", {
        method: "POST",
        body: {
          email: contactForm.email || undefined,
          phone: contactForm.phone || undefined,
        },
      });
      setMessage(result.message);
      setContactForm(initialContact);
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
          <h2>Request contact change</h2>
        </div>
        <p className="section-sub">
          Your current email and phone remain active until a school
          administrator approves the change. A confirmation is sent to your
          current email.
        </p>
        <form className="form" onSubmit={requestContactChange}>
          <div className="field">
            <label htmlFor="new-email">New email address</label>
            <input
              id="new-email"
              type="email"
              value={contactForm.email}
              onChange={(event) =>
                setContactForm({ ...contactForm, email: event.target.value })
              }
              placeholder={teacher?.email || "name@school.org"}
            />
          </div>
          <div className="field">
            <label htmlFor="new-phone">New mobile number</label>
            <input
              id="new-phone"
              value={contactForm.phone}
              onChange={(event) =>
                setContactForm({ ...contactForm, phone: event.target.value })
              }
              placeholder={teacher?.phone || "+233..."}
            />
          </div>
          <LoadingButton
            className="button button-primary"
            disabled={saving}
            loading={saving}
            type="submit"
          >
            {saving ? "Sending request..." : "Request approval"}
          </LoadingButton>
        </form>
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
          <LoadingButton
            className="button button-primary"
            disabled={saving}
            loading={saving}
            type="submit"
          >
            {saving ? "Updating..." : "Update password"}
          </LoadingButton>
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
