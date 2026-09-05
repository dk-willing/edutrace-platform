"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiRequest, clearAccessToken, getCurrentTeacher } from "../lib/api";

const nav = [
  ["⌂", "Overview", "/dashboard"],
  ["▦", "Classes", "/classes"],
  ["○", "Students", "/students"],
  ["⇧", "Imports", "/imports"],
  ["▤", "Reports", "/reports"],
];
const secondary = [
  ["!", "Notifications", "/notifications"],
  ["⚙", "Settings", "/settings"],
  ["◆", "Admin", "/admin"],
];

export function Workspace({ children, title, subtitle, action }) {
  const pathname = usePathname();
  const router = useRouter();
  const [teacher, setTeacher] = useState(null);
  const [loggingOut, setLoggingOut] = useState(false);
  useEffect(() => setTeacher(getCurrentTeacher()), []);
  const fullName = teacher
    ? `${teacher.firstName} ${teacher.lastName}`
    : "EduTrace user";
  const initials = teacher
    ? `${teacher.firstName?.[0] || ""}${teacher.lastName?.[0] || ""}`
    : "ET";
  const workspaceName = teacher?.school?.name || "EduTrace administration";
  async function logout() {
    setLoggingOut(true);
    try {
      await apiRequest("/api/v1/auth/logout", { method: "POST" });
    } catch {
      /* Clear local state even if the API is unavailable. */
    } finally {
      clearAccessToken();
      router.push("/login");
    }
  }
  return (
    <div className="workspace">
      <aside className="sidebar">
        <Link className="logo" href="/dashboard">
          <span className="logo-mark">ET</span>
          <span>EduTrace</span>
        </Link>
        <div className="side-label">Workspace</div>
        {nav.map(([icon, label, href]) => (
          <Link
            className={`side-link ${pathname === href ? "active" : ""}`}
            href={href}
            key={href}
          >
            <span className="side-icon">{icon}</span>
            <span>{label}</span>
          </Link>
        ))}
        <div className="side-label">Manage</div>
        {secondary.map(([icon, label, href]) => (
          <Link
            className={`side-link ${pathname === href ? "active" : ""}`}
            href={href}
            key={href}
          >
            <span className="side-icon">{icon}</span>
            <span>{label}</span>
          </Link>
        ))}
        <div className="sidebar-bottom">
          Demo environment
          <br />
          All learner records are fictional.
        </div>
      </aside>
      <section className="main">
        <header className="topbar">
          <span className="crumb">
            {workspaceName} / {title}
          </span>
          <div className="user-pill">
            <span>{fullName}</span>
            <span className="avatar">{initials}</span>
            <button
              className="logout-button"
              type="button"
              onClick={logout}
              disabled={loggingOut}
              title="Sign out"
            >
              {loggingOut ? "..." : "Sign out"}
            </button>
          </div>
        </header>
        <main className="content">
          <div className="content-head">
            <div>
              <h1>{title}</h1>
              <p>{subtitle}</p>
            </div>
            {action}
          </div>
          {children}
        </main>
      </section>
    </div>
  );
}

export function RiskBadge({ children }) {
  const cls = String(children).toLowerCase();
  return <span className={`badge badge-${cls}`}>{children}</span>;
}
