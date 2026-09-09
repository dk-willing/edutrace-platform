import Link from "next/link";
import { Workspace, RiskBadge } from "../../dashboard/Workspace";
export default function StudentPage() {
  return (
    <Workspace
      title="Amina Mensah"
      subtitle="ET-2041 · JHS 2A"
      action={<button className="button button-outline">More actions ▾</button>}
    >
      <div className="notice">
        <strong>Decision-support signal.</strong> Review the context below with
        the learner and relevant school staff. It is not a diagnosis or
        prediction of a fixed outcome.
      </div>
      <div className="stat-grid">
        <div className="stat">
          <div className="stat-label">Current signal</div>
          <div className="stat-value" style={{ fontSize: 26 }}>
            ELEVATED
          </div>
          <div className="stat-foot">Human review required</div>
        </div>
        <div className="stat">
          <div className="stat-label">Model output</div>
          <div className="stat-value">0.72</div>
          <div className="stat-foot">Human review required</div>
        </div>
        <div className="stat">
          <div className="stat-label">Attendance trend</div>
          <div className="stat-value">-8%</div>
          <div className="stat-foot">Last four weeks</div>
        </div>
        <div className="stat">
          <div className="stat-label">Open support</div>
          <div className="stat-value">2</div>
          <div className="stat-foot">One due Friday</div>
        </div>
      </div>
      <div className="grid-2">
        <section className="panel">
          <div className="panel-head">
            <h2>Contributing factors</h2>
            <span className="td-muted">Model explanation</span>
          </div>
          <div className="factor">
            <span>Recent attendance has declined</span>
            <span>Contributing</span>
          </div>
          <div className="factor">
            <span>Assessment completion is lower</span>
            <span>Contributing</span>
          </div>
          <div className="factor">
            <span>Previous term attendance</span>
            <span style={{ color: "var(--teal)" }}>Protective</span>
          </div>
          <p className="section-sub" style={{ fontSize: 12, marginTop: 20 }}>
            These factors contributed to the model's estimate. They do not
            establish cause.
          </p>
        </section>
        <section className="panel">
          <div className="panel-head">
            <h2>Recommended next steps</h2>
          </div>
          <div className="task">
            <span className="task-dot" />
            <div>
              <p>Review recent attendance context</p>
              <small>Suggested · high priority</small>
            </div>
          </div>
          <div className="task">
            <span className="task-dot" style={{ background: "var(--gold)" }} />
            <div>
              <p>Check assessment support needs</p>
              <small>Suggested · this week</small>
            </div>
          </div>
          <button className="button button-primary" style={{ marginTop: 14 }}>
            Start human review
          </button>
        </section>
      </div>
      <section className="panel page-card">
        <div className="panel-head">
          <h2>Student timeline</h2>
          <span className="td-muted">Recent activity</span>
        </div>
        <div className="task">
          <span className="task-dot" style={{ background: "var(--teal)" }} />
          <div>
            <p>Observation recorded</p>
            <small>Attendance and assessment data · 5 March 2026</small>
          </div>
        </div>
        <div className="task">
          <span className="task-dot" style={{ background: "var(--gold)" }} />
          <div>
            <p>Support follow-up scheduled</p>
            <small>Attendance conversation · due 8 March 2026</small>
          </div>
        </div>
      </section>
      <p className="form-foot">
        <Link href="/students">← Back to students</Link>
      </p>
    </Workspace>
  );
}
