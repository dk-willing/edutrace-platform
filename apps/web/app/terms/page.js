import Link from "next/link";
export default function TermsPage() {
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
        <div className="eyebrow">Terms of use</div>
        <h1>Use insight responsibly.</h1>
        <p className="hero-copy">
          EduTrace provides decision support for authorised school staff. It
          does not guarantee outcomes, diagnose medical or psychological
          conditions, or replace professional judgement.
        </p>
        <div className="panel page-card">
          <h3>Shared responsibilities</h3>
          <p className="section-sub">
            Schools must use the service lawfully, protect account access,
            review recommendations with appropriate context, and follow
            safeguarding obligations. Users must not use the service to label,
            punish, exclude, or make irreversible decisions about learners.
          </p>
          <h3 style={{ marginTop: 30 }}>Service limitations</h3>
          <p className="section-sub">
            Model availability, accuracy, SMS delivery, and generated
            recommendations may vary. Production scoring requires an explicitly
            approved model. Model outputs are decision-support signals and must
            be reviewed by authorised school staff.
          </p>
        </div>
      </main>
    </div>
  );
}
