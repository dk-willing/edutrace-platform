"use client";

import Link from "next/link";
import { useState } from "react";
import { apiRequest } from "../lib/api";

export default function RegisterPage() {
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setBusy(true);
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      const result = await apiRequest("/api/v1/auth/register", {
        method: "POST",
        body: Object.fromEntries(form.entries()),
      });
      setSuccess("Account created. Check your email to verify it.");
      formElement.reset();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-panel">
        <Link className="logo" href="/">
          <span className="logo-mark">ET</span>EduTrace
        </Link>
        <div>
          <div className="auth-kicker">Join your school</div>
          <p className="auth-aside">A shared view for thoughtful follow-up.</p>
          <p className="auth-note">
            Your school must already be onboarded by an administrator before you
            register.
          </p>
        </div>
        <p className="auth-note">
          Your school identity is verified on the server.
        </p>
      </div>
      <div className="auth-panel">
        <div className="form-wrap">
          <div className="eyebrow">Teacher registration</div>
          <h1>Create your account</h1>
          <p className="form-intro">
            Tell us who you are and which school you belong to.
          </p>
          {error && (
            <div className="notice" role="alert">
              {error}
            </div>
          )}
          {success && (
            <div className="notice" role="status">
              {success}
            </div>
          )}
          <form className="form" onSubmit={submit}>
            <div
              className="feature-grid"
              style={{ gridTemplateColumns: "1fr 1fr", gap: 10 }}
            >
              <div className="field">
                <label htmlFor="first">First name</label>
                <input id="first" name="firstName" required placeholder="Ama" />
              </div>
              <div className="field">
                <label htmlFor="last">Last name</label>
                <input
                  id="last"
                  name="lastName"
                  required
                  placeholder="Mensah"
                />
              </div>
            </div>
            <div className="field">
              <label htmlFor="school">School code</label>
              <input
                id="school"
                name="schoolCode"
                required
                placeholder="ABC-JHS"
              />
            </div>
            <div className="field">
              <label htmlFor="email">Work email</label>
              <input
                id="email"
                name="email"
                required
                type="email"
                placeholder="you@school.edu.gh"
              />
            </div>
            <div className="field">
              <label htmlFor="phone">Mobile number</label>
              <input
                id="phone"
                name="phone"
                required
                type="tel"
                placeholder="024 000 0000"
                autoComplete="tel"
              />
            </div>
            <div className="field">
              <label htmlFor="password">Create password</label>
              <input
                id="password"
                name="password"
                minLength={12}
                required
                type="password"
                placeholder="At least 12 characters"
              />
            </div>
            <div className="field">
              <label htmlFor="password-confirmation">Confirm password</label>
              <input
                id="password-confirmation"
                name="passwordConfirmation"
                minLength={12}
                required
                type="password"
                placeholder="Repeat your password"
                autoComplete="new-password"
              />
            </div>
            <button
              className="button button-primary"
              disabled={busy}
              type="submit"
            >
              {busy ? "Creating account..." : "Create account"}
            </button>
          </form>
          <p className="form-foot">
            Already registered? <Link href="/login">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
