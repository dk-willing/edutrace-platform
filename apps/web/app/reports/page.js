"use client";

import { useEffect, useState } from "react";
import { Workspace, riskTierLabel } from "../dashboard/Workspace";
import { apiRequest, downloadFile } from "../lib/api";
import { PageSkeleton } from "../components/PageSkeleton";

export default function ReportsPage() {
  const [report, setReport] = useState(null);
  const [analysisReports, setAnalysisReports] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.allSettled([
      apiRequest("/api/v1/reports/school"),
      apiRequest("/api/v1/reports/analysis"),
    ]).then(([result, history]) => {
      if (result.status === "fulfilled") setReport(result.value.report);
      else setError(result.reason.message);
      if (history.status === "fulfilled") {
        setAnalysisReports(history.value.reports || []);
      } else if (result.status === "fulfilled") {
        setError(history.reason.message);
      }
    });
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
        <PageSkeleton rows={6} cards={4} />
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
              <div className="stat-label">Analysis runs</div>
              <div className="stat-value">
                {report.analysisReportCount || 0}
              </div>
              <div className="stat-foot">Saved reports</div>
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
            <p className="section-sub">
              These labels show which students may benefit from additional
              support. They are signals for human review, not conclusions about
              a student.
            </p>
            {report.latestAnalysis && (
              <div className="notice" role="status">
                Latest run:{" "}
                {report.latestAnalysis.filename || report.latestAnalysis.source}{" "}
                · {report.latestAnalysis.rowsScored}/
                {report.latestAnalysis.totalRows} rows scored on{" "}
                {new Date(report.latestAnalysis.createdAt).toLocaleString()}.
              </div>
            )}

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
                    <label>{riskTierLabel(tier)}</label>
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
          <section className="panel page-card">
            <div className="panel-head">
              <h2>Analysis history</h2>
              <span className="td-muted">
                {analysisReports.length} report
                {analysisReports.length === 1 ? "" : "s"}
              </span>
            </div>
            {!analysisReports.length ? (
              <div className="empty-state compact">
                <h3>No analysis runs yet</h3>
                <p>Each risk analysis run will be saved here.</p>
              </div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Source</th>
                      <th>Rows</th>
                      <th>Urgent support</th>
                      <th>Model</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {analysisReports.map((item) => (
                      <tr key={item.id}>
                        <td>{new Date(item.createdAt).toLocaleString()}</td>
                        <td>{item.filename || item.source}</td>
                        <td>
                          {item.rowsScored}/{item.totalRows}
                        </td>
                        <td>{item.highCount}</td>
                        <td>{item.modelVersion || "Unavailable"}</td>
                        <td>
                          <button
                            className="panel-link"
                            onClick={() =>
                              downloadFile(
                                `/api/v1/reports/analysis/${item.id}/download`,
                                `edutrace-report-${item.id}.pdf`,
                              )
                            }
                            type="button"
                          >
                            Download PDF
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </Workspace>
  );
}
