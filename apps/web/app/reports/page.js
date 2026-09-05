"use client";

import { useEffect, useState } from "react";
import { Workspace } from "../dashboard/Workspace";
import { apiRequest } from "../lib/api";

export default function ReportsPage() {
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiRequest("/api/v1/reports/school")
      .then((result) => setReport(result.report))
      .catch((requestError) => setError(requestError.message));
  }, []);

  return (
    <Workspace
      title="Reports"
      subtitle="Reports generated from your school data and recorded model assessments"
    >
      <div className="notice">
        <strong>Model governance:</strong> reports never invent scores. If no
        approved model assessments have been recorded, the report says so.
      </div>

      {error && (
        <div className="notice" role="alert">
          {error}
        </div>
      )}

      {!report ? (
        <div className="panel empty-state">
          <h2>Loading report</h2>
          <p>Preparing your school report...</p>
        </div>
      ) : (
        <>
          <div className="stat-grid">
            <div className="stat">
              <div className="stat-label">Students</div>
              <div className="stat-value">{report.students}</div>
              <div className="stat-foot">Active records</div>
            </div>
            <div className="stat">
              <div className="stat-label">Observations</div>
              <div className="stat-value">{report.observations}</div>
              <div className="stat-foot">Stored school data</div>
            </div>
            <div className="stat">
              <div className="stat-label">Assessments</div>
              <div className="stat-value">{report.assessments}</div>
              <div className="stat-foot">Recorded model outputs</div>
            </div>
            <div className="stat">
              <div className="stat-label">Model</div>
              <div className="stat-value" style={{ fontSize: "20px" }}>
                {report.model?.modelVersion || "Unavailable"}
              </div>
              <div className="stat-foot">
                {report.model?.status || "No approved output"}
              </div>
            </div>
          </div>

          <section className="panel page-card">
            <div className="panel-head">
              <h2>School report</h2>
              <span className="td-muted">
                Generated {new Date(report.generatedAt).toLocaleString()}
              </span>
            </div>

            {report.assessments === 0 ? (
              <div className="empty-state">
                <h2>No model report available</h2>
                <p>
                  There are no recorded model assessments for your classes. CSV
                  import stores observations first; scoring remains unavailable
                  until an approved production model is active.
                </p>
              </div>
            ) : (
              <div className="risk-list">
                {["LOW", "WATCH", "ELEVATED", "HIGH"].map((tier) => (
                  <div className="risk-line" key={tier}>
                    <label>{tier}</label>
                    <div className="risk-track">
                      <div
                        className={`risk-fill ${tier.toLowerCase()}`}
                        style={{
                          width: `${
                            ((report.riskDistribution[tier] || 0) /
                              report.assessments) *
                            100
                          }%`,
                        }}
                      />
                    </div>
                    <span className="risk-count">
                      {report.riskDistribution[tier] || 0}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </Workspace>
  );
}
