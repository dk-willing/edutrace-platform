"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Workspace } from "../dashboard/Workspace";
import { apiRequest } from "../lib/api";

const emptyForm = {
  name: "",
  gradeLevel: "JHS1",
  academicYear: new Date().getFullYear(),
};

export default function ClassesPage() {
  const [classes, setClasses] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  async function loadClasses() {
    try {
      const result = await apiRequest("/api/v1/classes");
      setClasses(result.classes || []);
    } catch (requestError) {
      setError(requestError.message);
    }
  }
  useEffect(() => {
    loadClasses();
  }, []);
  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await apiRequest("/api/v1/classes", {
        method: "POST",
        body: { ...form, academicYear: Number(form.academicYear) },
      });
      setForm(emptyForm);
      setOpen(false);
      await loadClasses();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <Workspace
      title="Classes"
      subtitle="Create and manage your own classes."
      action={
        <button
          className="button button-primary"
          type="button"
          onClick={() => setOpen(!open)}
        >
          + Create class
        </button>
      }
    >
      {error && (
        <div className="notice" role="alert">
          {error}
        </div>
      )}
      {open && (
        <section className="panel page-card">
          <div className="panel-head">
            <h2>Create a class</h2>
            <button
              className="button button-quiet"
              type="button"
              onClick={() => setOpen(false)}
            >
              Cancel
            </button>
          </div>
          <form className="form" onSubmit={submit}>
            <div className="field">
              <label htmlFor="class-name">Class name</label>
              <input
                id="class-name"
                required
                value={form.name}
                onChange={(event) =>
                  setForm({ ...form, name: event.target.value })
                }
                placeholder="JHS 2A"
              />
            </div>
            <div
              className="feature-grid"
              style={{ gridTemplateColumns: "1fr 1fr", gap: 10 }}
            >
              <div className="field">
                <label htmlFor="grade">Grade level</label>
                <select
                  id="grade"
                  value={form.gradeLevel}
                  onChange={(event) =>
                    setForm({ ...form, gradeLevel: event.target.value })
                  }
                >
                  <option value="JHS1">JHS 1</option>
                  <option value="JHS2">JHS 2</option>
                  <option value="JHS3">JHS 3</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="year">Academic year</label>
                <input
                  id="year"
                  required
                  type="number"
                  min="2000"
                  max="2200"
                  value={form.academicYear}
                  onChange={(event) =>
                    setForm({ ...form, academicYear: event.target.value })
                  }
                />
              </div>
            </div>
            <button
              className="button button-primary"
              disabled={saving}
              type="submit"
            >
              {saving ? "Creating..." : "Create class"}
            </button>
          </form>
        </section>
      )}
      {classes.length === 0 ? (
        <section className="panel empty-state">
          <div className="eyebrow">Your workspace</div>
          <h2>No classes yet</h2>
          <p>
            Create your first class to begin adding students. Classes are
            private to your school and owned by you.
          </p>
          <button
            className="button button-primary"
            type="button"
            onClick={() => setOpen(true)}
          >
            Create your first class
          </button>
        </section>
      ) : (
        <div className="feature-grid">
          {classes.map((classItem) => (
            <article className="feature" key={classItem.id}>
              <div className="feature-num">YOUR CLASS</div>
              <h3>{classItem.name}</h3>
              <p>
                {classItem._count?.students || 0} students ·{" "}
                {classItem.academicYear} · {classItem.gradeLevel}
              </p>
              <Link
                className="button button-outline"
                href={`/students?classId=${classItem.id}`}
              >
                Open class
              </Link>
            </article>
          ))}
        </div>
      )}
    </Workspace>
  );
}
