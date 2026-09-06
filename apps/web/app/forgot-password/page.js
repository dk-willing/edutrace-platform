"use client";

import Link from "next/link";
import { useState } from "react";
import { apiRequest } from "../lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await apiRequest("/api/v1/auth/forgot-password", {
        method: "POST",
        body: { email },
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
          {" "}
          <span className="logo-mark">ET</span>EduTrace
        </Link>
        <div>
          <div className="auth-kicker">Account recovery</div>
          <p className="auth-aside">Get back to your school workspace.</p>
        </div>
      </div>
      <div className="auth-panel">
        <div className="form-wrap">
          <div className="eyebrow">Forgot password</div>
          <h1>Reset your password</h1>
          <p className="form-intro">
            Enter your work email. If an account matches, reset instructions
            will be sent.
          </p>
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
              <label htmlFor="email">Work email</label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>
            <button
              className="button button-primary"
              disabled={busy}
              type="submit"
            >
              {busy ? "Sending..." : "Send reset instructions"}
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
