import { Workspace } from "../dashboard/Workspace";
export default function NotificationsPage() {
  return (
    <Workspace
      title="Tasks & notifications"
      subtitle="The next useful thing, in one place"
    >
      <section className="panel">
        <div className="task">
          <span className="task-dot" />
          <div>
            <p>Review Amina Mensah's latest signal</p>
            <small>Elevated · due today · JHS 2A</small>
          </div>
          <button className="button button-quiet">Open</button>
        </div>
        <div className="task">
          <span className="task-dot" style={{ background: "var(--gold)" }} />
          <div>
            <p>Follow up on Kojo Owusu's attendance</p>
            <small>Support action · due today · JHS 2A</small>
          </div>
          <button className="button button-quiet">Open</button>
        </div>
        <div className="task">
          <span className="task-dot" style={{ background: "var(--teal)" }} />
          <div>
            <p>CSV import completed</p>
            <small>JHS2A_students.csv · 32 accepted rows</small>
          </div>
          <button className="button button-quiet">View</button>
        </div>
      </section>
    </Workspace>
  );
}
