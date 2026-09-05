import { Workspace } from "../dashboard/Workspace";
export default function SettingsPage() {
  return (
    <Workspace title="Settings" subtitle="Your account and school workspace">
      <section className="panel">
        <div className="panel-head">
          <h2>Account</h2>
        </div>
        <div className="form">
          <div className="field">
            <label htmlFor="name">Name</label>
            <input id="name" value="Ama Mensah" readOnly />
          </div>
          <div className="field">
            <label htmlFor="email">Verified email</label>
            <input id="email" value="ama.mensah@example.edu.gh" readOnly />
          </div>
          <div className="field">
            <label htmlFor="school">School</label>
            <input id="school" value="ABC Junior High · ABC-JHS" readOnly />
          </div>
        </div>
      </section>
      <section className="panel page-card">
        <div className="panel-head">
          <h2>Privacy controls</h2>
        </div>
        <p className="section-sub">
          Your access is determined by your verified school account. Sensitive
          safeguarding disclosures are never shown in student timelines or sent
          to the model.
        </p>
        <button className="button button-outline">Request my data</button>
      </section>
    </Workspace>
  );
}
