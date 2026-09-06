"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { apiRequest } from "../lib/api";

function ResetPasswordForm() {
  const params = useSearchParams();
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await apiRequest("/api/v1/auth/reset-password", {
        method: "POST",
        body: { token: params.get("token"), password, passwordConfirmation },
      });
      setMessage(result.message);
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
          <div className="auth-kicker">Account recovery</div>
          <p className="auth-aside">Choose a new password.</p>
        </div>
      </div>
      <div className="auth-panel">
        <div className="form-wrap">
          <div className="eyebrow">Reset password</div>
          <h1>Set a new password</h1>
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
          <form className="form" onSubmit={submit}>
            <div className="field">
              <label htmlFor="password">New password</label>
              <input
                id="password"
                minLength={12}
                required
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="new-password"
              />
            </div>
            <div className="field">
              <label htmlFor="password-confirmation">
                Confirm new password
              </label>
              <input
                id="password-confirmation"
                minLength={12}
                required
                type="password"
                value={passwordConfirmation}
                onChange={(event) =>
                  setPasswordConfirmation(event.target.value)
                }
                autoComplete="new-password"
              />
            </div>
            <button
              className="button button-primary"
              disabled={busy}
              type="submit"
            >
              {busy ? "Updating..." : "Update password"}
            </button>
          </form>
          <p className="form-foot">
            <Link href="/login">Back to sign in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<div className="auth-page" aria-busy="true" />}>
      <ResetPasswordForm />
    </Suspense>
  );
}
