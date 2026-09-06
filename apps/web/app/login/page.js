"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiRequest, setAccessToken, setCurrentTeacher } from "../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setError("");
    setBusy(true);
    const form = new FormData(event.currentTarget);
    try {
      const result = await apiRequest("/api/v1/auth/login", {
        method: "POST",
        body: { email: form.get("email"), password: form.get("password") },
      });
      setAccessToken(result.accessToken);
      setCurrentTeacher(result.teacher);
      router.push(
        result.teacher?.role === "SYSTEM_ADMIN" ? "/admin" : "/dashboard",
      );
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
          <div className="auth-kicker">Teacher workspace</div>
          <p className="auth-aside">Good work starts with a clearer view.</p>
          <p className="auth-note">
            Sign in to see your school, classes, review tasks, and student
            support activity.
          </p>
        </div>
        <p className="auth-note">
          Decision support for people who know their learners.
        </p>
      </div>
      <div className="auth-panel">
        <div className="form-wrap">
          <div className="eyebrow">Welcome back</div>
          <h1>Sign in</h1>
          <p className="form-intro">
            Use your verified school account to continue.
          </p>
          {error && (
            <div className="notice" role="alert">
              {error}
            </div>
          )}
          <form className="form" onSubmit={submit}>
            <div className="field">
              <label htmlFor="email">Email address</label>
              <input
                id="email"
                name="email"
                required
                type="email"
                placeholder="you@school.edu.gh"
              />
            </div>
            <div className="field">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                name="password"
                required
                minLength={12}
                type="password"
                placeholder="Your password"
              />
            </div>
            <button
              className="button button-primary"
              disabled={busy}
              type="submit"
            >
              {busy ? "Signing in..." : "Sign in"}
            </button>
          </form>
          <p className="form-foot">
            <Link href="/forgot-password">Forgot your password?</Link>
          </p>
          <p className="form-foot">
            Need an account? <Link href="/register">Register as a teacher</Link>
          </p>
          <p className="form-foot">
            <Link href="/">Return to homepage</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
