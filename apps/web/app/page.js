import Link from "next/link";
import LegalModal from "./components/LegalModal";

const features = [
  [
    "01",
    "Notice earlier",
    "Bring attendance, learning, and access signals together in one calm view.",
  ],
  [
    "02",
    "Understand context",
    "See contributing factors without reducing a learner to a label.",
  ],
  [
    "03",
    "Support deliberately",
    "Turn insight into practical follow-up, human review, and care.",
  ],
];

export default function HomePage() {
  return (
    <div className="shell">
      <header className="site-nav">
        <Link className="logo" href="/">
          <span className="logo-mark">ET</span>EduTrace
        </Link>
        <nav className="nav-links">
          <Link href="#approach">Our approach</Link>
          <Link href="#safeguarding">Safeguarding</Link>
          <LegalModal type="privacy" />
          <Link href="/login" className="button button-dark">
            Sign in
          </Link>
        </nav>
      </header>
      <main>
        <section className="hero">
          <div className="hero-grid">
            <div>
              <div className="eyebrow">For schools in Ghana</div>
              <h1>Notice the change. Make room for support.</h1>
              <p className="hero-copy">
                EduTrace helps teachers understand which learners may need
                attention, why a signal matters, and what a thoughtful next step
                could be.
              </p>
              <div className="hero-actions">
                <Link className="button button-primary" href="/register">
                  Get started <span>↗</span>
                </Link>
                <Link className="button button-outline" href="#approach">
                  See how it works
                </Link>
              </div>
            </div>
            <div className="hero-visual">
              <div className="hero-card">
                <div className="card-top">
                  <div>
                    <div className="student-name">Amina Mensah</div>
                    <div className="student-meta">
                      JHS 2A · Learner overview
                    </div>
                  </div>
                  <span className="risk-badge">ELEVATED</span>
                </div>
                <div className="score-row">
                  <div className="score">72</div>
                  <div className="score-label">
                    estimated attention
                    <br />
                    signal · decision support
                  </div>
                </div>
                <div className="mini-bars">
                  <i style={{ height: "38%" }} />
                  <i style={{ height: "56%" }} />
                  <i style={{ height: "49%" }} />
                  <i style={{ height: "72%" }} />
                  <i style={{ height: "64%" }} />
                  <i style={{ height: "83%" }} />
                </div>
                <div className="factor">
                  <span>Recent attendance trend</span>
                  <span>Contributing</span>
                </div>
                <div className="factor">
                  <span>Assessment completion</span>
                  <span>Review</span>
                </div>
              </div>
            </div>
          </div>
        </section>
        <section className="section" id="approach">
          <div className="section-head">
            <div>
              <div className="eyebrow">A better rhythm</div>
              <h2>Identify → understand → support.</h2>
            </div>
            <p className="section-sub">
              The platform is designed around the work teachers already do:
              noticing, asking, acting, and checking back in.
            </p>
          </div>
          <div className="feature-grid">
            {features.map(([number, title, body]) => (
              <article className="feature" key={number}>
                <div className="feature-num">{number}</div>
                <h3>{title}</h3>
                <p>{body}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="band" id="safeguarding">
          <div className="section">
            <div className="eyebrow">Human-centred by design</div>
            <p className="quote">
              A model can surface a question. Only people can understand the
              whole story.
            </p>
            <p className="section-sub">
              Every insight is a decision-support signal, never a diagnosis or
              an irreversible judgement. Safeguarding concerns follow a
              separate, structured referral path.
            </p>
          </div>
        </section>
        <section className="section">
          <div className="section-head">
            <div>
              <div className="eyebrow">Built for the school day</div>
              <h2>Less hunting. More helping.</h2>
            </div>
            <p className="section-sub">
              From a class overview to a student timeline, useful context stays
              close to the action.
            </p>
          </div>
          <div className="feature-grid">
            <article className="feature">
              <div className="feature-num">CLASS VIEW</div>
              <h3>One clear picture</h3>
              <p>
                See attendance shifts, review tasks, and support activity
                without a spreadsheet maze.
              </p>
            </article>
            <article className="feature">
              <div className="feature-num">EXPLAINABLE</div>
              <h3>Reasons, not verdicts</h3>
              <p>
                Contributing factors are presented as prompts for conversation,
                with the model's limitations in view.
              </p>
            </article>
            <article className="feature">
              <div className="feature-num">PRIVATE</div>
              <h3>Careful with data</h3>
              <p>
                Identity information is separated from model features, with
                school-level access controls.
              </p>
            </article>
          </div>
        </section>
      </main>
      <footer className="footer">
        <div className="footer-inner">
          <span>© 2026 EduTrace</span>
          <span>
            <LegalModal type="privacy" /> · <LegalModal type="terms" /> ·{" "}
            <Link href="/login">Sign in</Link>
          </span>
        </div>
      </footer>
    </div>
  );
}
