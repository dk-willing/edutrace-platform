"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Workspace, RiskBadge, riskTierLabel } from "./Workspace";
import { apiRequest, getCurrentTeacher } from "../lib/api";
import { PageSkeleton } from "../components/PageSkeleton";

const tiers = ["LOW", "WATCH", "ELEVATED", "HIGH"];

export default function DashboardPage() {
  const [teacher, setTeacher] = useState(null);
  const [greeting, setGreeting] = useState("Good morning");
  const [dashboard, setDashboard] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    setTeacher(getCurrentTeacher());
    const hour = new Date().getHours();
    setGreeting(
      hour < 12
        ? "Good morning"
        : hour < 18
          ? "Good afternoon"
          : "Good evening",
    );
    let active = true;
    const loadDashboard = () =>
      apiRequest("/api/v1/dashboard")
        .then((result) => {
          if (active) {
            setDashboard(result);
            setError("");
          }
        })
        .catch((requestError) => {
          if (active) setError(requestError.message);
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    loadDashboard();
    const refreshTimer = window.setInterval(loadDashboard, 15000);
    return () => {
      active = false;
      window.clearInterval(refreshTimer);
    };
  }, []);
  const firstName = teacher?.firstName || "there";
  const stats = dashboard?.stats;
  const totalRisk = Object.values(stats?.riskDistribution || {}).reduce(
    (sum, value) => sum + value,
    0,
  );
  const recentAssessments = dashboard?.recentAssessments || [];
  const analysisResults = dashboard?.latestReport?.results || [];
  return (
    <Workspace
      title={`${greeting}, ${firstName}`}
      subtitle={
        stats
          ? `${stats.classCount} class${stats.classCount === 1 ? "" : "es"} in your workspace`
          : "Your school workspace"
      }
      variant="dashboard"
    >
      {error && (
        <div className="notice" role="alert">
          {error}
        </div>
      )}
      {loading ? (
        <PageSkeleton rows={5} cards={4} />
      ) : (
        <>
          <div className="stat-grid">
            <div className="stat">
              <div className="stat-label">Students in view</div>
              <div className="stat-value">{stats?.studentCount || 0}</div>
              <div className="stat-foot">Your classes</div>
            </div>
            <div className="stat">
              <div className="stat-label">Uploaded observations</div>
              <div className="stat-value">{stats?.observationCount || 0}</div>
              <div className="stat-foot">Attendance and school data</div>
            </div>
            <div className="stat">
              <div className="stat-label">Needs attention</div>
              <div className="stat-value">
                {(stats?.riskDistribution?.ELEVATED || 0) +
                  (stats?.riskDistribution?.HIGH || 0)}
              </div>
              <div className="stat-foot">Recorded assessments</div>
            </div>
            <div className="stat">
              <div className="stat-label">Awaiting review</div>
              <div className="stat-value">{stats?.awaitingReview || 0}</div>
              <div className="stat-foot">Human review required</div>
            </div>
            <div className="stat">
              <div className="stat-label">Open follow-ups</div>
              <div className="stat-value">{stats?.openInterventions || 0}</div>
              <div className="stat-foot">Open interventions</div>
            </div>
            <div className="stat">
              <div className="stat-label">Analysis reports</div>
              <div className="stat-value">
                {stats?.analysisReportCount || 0}
              </div>
              <div className="stat-foot">Saved scoring runs</div>
            </div>
            <div className="stat">
              <div className="stat-label">Accepted follow-ups</div>
              <div className="stat-value">
                {stats?.acceptedReviewCount || 0}
              </div>
              <div className="stat-foot">Confirmed by a teacher</div>
            </div>
          </div>
          {stats?.classCount === 0 && (
            <div className="notice">
              <strong>No classes yet.</strong> Go to{" "}
              <Link className="panel-link" href="/classes">
                Classes
              </Link>{" "}
              to create your first class.
            </div>
          )}
          <div className="grid-2">
            <section className="panel">
              <div className="panel-head">
                <h2>Recorded risk assessments</h2>
                <Link className="panel-link" href="/students">
                  View students ↗
                </Link>
              </div>
              {totalRisk === 0 && analysisResults.length === 0 ? (
                <div className="empty-state compact">
                  <h3>No assessments yet</h3>
                  <p>
                    Risk analysis results will appear here after a scoring run.
                  </p>
                </div>
              ) : totalRisk === 0 ? (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Student</th>
                        <th>Risk</th>
                        <th>Signal</th>
                        <th>Review</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analysisResults.slice(0, 8).map((item, index) => (
                        <tr key={item.student_key || index}>
                          <td>{item.student_name || item.student_key}</td>
                          <td>{(Number(item.risk || 0) * 100).toFixed(1)}%</td>
                          <td>
                            <RiskBadge>{item.tier}</RiskBadge>
                          </td>
                          <td>
                            <span className="badge badge-watch">
                              Waiting for review
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="risk-list">
                  {tiers.map((tier) => {
                    const count = stats.riskDistribution?.[tier] || 0;
                    return (
                      <div className="risk-line" key={tier}>
                        <label>{riskTierLabel(tier)}</label>
                        <div className="risk-track">
                          <div
                            className={`risk-fill ${tier.toLowerCase()}`}
                            style={{ width: `${(count / totalRisk) * 100}%` }}
                          />
                        </div>
                        <span className="risk-count">{count}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
            <section className="panel">
              <div className="panel-head">
                <h2>Tasks requiring attention</h2>
                <Link className="panel-link" href="/notifications">
                  All tasks
                </Link>
              </div>
              {(stats?.awaitingReview || 0) === 0 &&
              (stats?.acceptedReviewCount || 0) === 0 &&
              (stats?.openInterventions || 0) === 0 ? (
                <div className="empty-state compact">
                  <h3>Nothing requiring attention</h3>
                  <p>New reviews and follow-ups will appear here.</p>
                </div>
              ) : (
                <div className="task">
                  <span className="task-dot" />
                  <div>
                    {stats.awaitingReview > 0 && (
                      <p>
                        {stats.awaitingReview} assessment
                        {stats.awaitingReview === 1 ? "" : "s"} awaiting review
                      </p>
                    )}
                    {stats.acceptedReviewCount > 0 && (
                      <p>
                        {stats.acceptedReviewCount} assessment
                        {stats.acceptedReviewCount === 1 ? "" : "s"} accepted
                        for follow-up
                      </p>
                    )}
                    <small>Open the student list to review or follow up</small>
                  </div>
                </div>
              )}
            </section>
          </div>
          <section className="panel page-card">
            <div className="panel-head">
              <h2>Recent assessments</h2>
              <Link className="panel-link" href="/students">
                Open student list ↗
              </Link>
            </div>
            {recentAssessments.length === 0 ? (
              <div className="empty-state compact">
                <h3>No recent assessments</h3>
                <p>
                  Student assessment history will appear here when available.
                </p>
              </div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Student</th>
                      <th>Class</th>
                      <th>Signal</th>
                      <th>Model</th>
                      <th>Review</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentAssessments.map((assessment) => (
                      <tr key={assessment.id}>
                        <td>
                          <strong>
                            {assessment.student.identity?.studentName ||
                              "Unnamed student"}
                          </strong>
                          <div className="td-muted">
                            {assessment.student.externalId ||
                              assessment.student.studentKey.slice(0, 8)}
                          </div>
                        </td>
                        <td>
                          {assessment.student.class?.name || "Unassigned"}
                        </td>
                        <td>
                          <RiskBadge>{assessment.tier}</RiskBadge>
                        </td>
                        <td className="td-muted">
                          {assessment.modelRegistration.modelVersion}
                        </td>
                        <td>
                          {assessment.reviewOutcome ? (
                            <span className="badge badge-low">
                              {assessment.reviewOutcome.decision}
                            </span>
                          ) : (
                            <Link
                              className="panel-link"
                              href={`/students/${assessment.student.id}`}
                            >
                              {assessment.reviewViewedAt
                                ? "Opened, awaiting decision ↗"
                                : "Waiting to be opened ↗"}
                            </Link>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
          {dashboard?.latestReport && (
            <section className="panel page-card">
              <div className="panel-head">
                <h2>Latest analysis run</h2>
                <Link className="panel-link" href="/reports">
                  View reports ↗
                </Link>
              </div>
              <p className="section-sub">
                Latest student risk analysis results
              </p>
              <div className="risk-list">
                {tiers.map((tier) => (
                  <div className="risk-line" key={tier}>
                    <label>{riskTierLabel(tier)}</label>
                    <span className="risk-count">
                      {dashboard.latestReport.tierCounts?.[tier] || 0}
                    </span>
                  </div>
                ))}
              </div>
              {dashboard.latestReport.results?.length > 0 && (
                <div className="table-wrap" style={{ marginTop: "20px" }}>
                  <table>
                    <thead>
                      <tr>
                        <th>Student</th>
                        <th>Risk</th>
                        <th>Signal</th>
                        <th>Review</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analysisResults.slice(0, 8).map((item, index) => (
                        <tr key={item.student_key || index}>
                          <td>{item.student_name || item.student_key}</td>
                          <td>{(Number(item.risk || 0) * 100).toFixed(1)}%</td>
                          <td>
                            <RiskBadge>{item.tier}</RiskBadge>
                          </td>
                          <td>
                            <span className="badge badge-watch">
                              Waiting for review
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}
        </>
      )}
    </Workspace>
  );
}
