"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { apiRequest } from "../lib/api";

export default function VerifyEmailPage() {
  const searchParams = useSearchParams();
  const [state, setState] = useState({
    status: "loading",
    message: "Verifying your email...",
  });

  useEffect(() => {
    const token = searchParams.get("token");
    if (!token) {
      setState({
        status: "error",
        message: "This verification link is missing its token.",
      });
      return;
    }
    apiRequest("/api/v1/auth/verify-email", { method: "POST", body: { token } })
      .then(() =>
        setState({
          status: "success",
          message:
            "Your email is verified. Your school administrator can now approve your account.",
        }),
      )
      .catch((error) => setState({ status: "error", message: error.message }));
  }, [searchParams]);

  return (
    <div className="auth-page">
      <div className="auth-panel">
        <Link className="logo" href="/">
          <span className="logo-mark">ET</span>EduTrace
        </Link>
        <div>
          <div className="auth-kicker">Account verification</div>
          <p className="auth-aside">
            One small step, then back to the school day.
          </p>
          <p className="auth-note">
            Verification confirms ownership of your email address. It does not
            replace school approval.
          </p>
        </div>
      </div>
      <div className="auth-panel">
        <div className="form-wrap">
          <div className="eyebrow">Email verification</div>
          <h1>
            {state.status === "loading"
              ? "Checking your link"
              : state.status === "success"
                ? "Email verified"
                : "Verification failed"}
          </h1>
          <div
            className={`notice verify-${state.status}`}
            role={state.status === "error" ? "alert" : "status"}
          >
            {state.message}
          </div>
          {state.status !== "loading" && (
            <Link className="button button-primary" href="/login">
              Continue to sign in
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
