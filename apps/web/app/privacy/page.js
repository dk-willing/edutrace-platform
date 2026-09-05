import Link from "next/link";
export default function PrivacyPage() {
  return (
    <div className="shell">
      <header className="site-nav">
        <Link className="logo" href="/">
          <span className="logo-mark">ET</span>EduTrace
        </Link>
        <Link className="button button-outline" href="/">
          Back home
        </Link>
      </header>
      <main className="section">
        <div className="eyebrow">Privacy notice</div>
        <h1>Privacy, with care.</h1>
        <p className="hero-copy">
          EduTrace is designed to minimise data, separate identity from model
          features, and keep school decisions with authorised people.
        </p>
        <div className="panel page-card">
          <h3>What matters</h3>
          <p className="section-sub">
            Schools remain responsible for lawful notices, access decisions,
            retention, and appropriate safeguarding practice. EduTrace does not
            diagnose learners or make disciplinary decisions. Student
            information is access-controlled and model requests use pseudonymous
            keys where possible.
          </p>
          <h3 style={{ marginTop: 30 }}>Before production use</h3>
          <p className="section-sub">
            This notice is product guidance, not legal advice. A qualified
            privacy professional should review the final policy and processing
            arrangements for the school and Ghanaian context before real learner
            data is processed.
          </p>
        </div>
      </main>
    </div>
  );
}
