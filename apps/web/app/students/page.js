"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Workspace } from "../dashboard/Workspace";
import { apiRequest } from "../lib/api";

export default function StudentsPage() {
  const [students, setStudents] = useState([]);
  const [classes, setClasses] = useState([]);
  const [search, setSearch] = useState("");
  const [classId, setClassId] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    apiRequest("/api/v1/classes")
      .then((result) => setClasses(result.classes || []))
      .catch((requestError) => setError(requestError.message));
  }, []);
  useEffect(() => {
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams();
        if (search) params.set("search", search);
        if (classId) params.set("classId", classId);
        params.set("pageSize", "100");
        const firstPage = await apiRequest(`/api/v1/students?${params}`);
        const remainingPages = Array.from(
          { length: Math.max(0, (firstPage.pagination?.pages || 1) - 1) },
          (_, index) => index + 2,
        );
        const rest = await Promise.all(
          remainingPages.map((page) =>
            apiRequest(`/api/v1/students?${params}&page=${page}`),
          ),
        );
        setStudents([
          ...(firstPage.students || []),
          ...rest.flatMap((page) => page.students || []),
        ]);
        setError("");
      } catch (requestError) {
        setError(requestError.message);
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [search, classId]);
  return (
    <Workspace
      title="Students"
      subtitle={`${students.length} student${students.length === 1 ? "" : "s"} in your school`}
    >
      {error && (
        <div className="notice" role="alert">
          {error}
        </div>
      )}
      <div className="panel">
        <div className="panel-head">
          <div className="field" style={{ maxWidth: 340 }}>
            <label htmlFor="search">Search students</label>
            <input
              id="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Name or student ID"
            />
          </div>
          <div className="field" style={{ minWidth: 190 }}>
            <label htmlFor="class-filter">Class</label>
            <select
              id="class-filter"
              value={classId}
              onChange={(event) => setClassId(event.target.value)}
            >
              <option value="">All classes</option>
              {classes.map((classItem) => (
                <option key={classItem.id} value={classItem.id}>
                  {classItem.name}
                </option>
              ))}
            </select>
          </div>
        </div>
        {loading ? (
          <p className="section-sub">Loading students...</p>
        ) : students.length === 0 ? (
          <div className="empty-state compact">
            <h3>No students found</h3>
            <p>
              Try a different search or create a class and add students first.
            </p>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Class</th>
                  <th>Grade</th>
                  <th>Student ID</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {students.map((student) => (
                  <tr key={student.id}>
                    <td>
                      <strong>
                        {student.identity?.studentName || "Unnamed student"}
                      </strong>
                    </td>
                    <td>{student.class?.name || "Unassigned"}</td>
                    <td>{student.gradeLevel}</td>
                    <td className="td-muted">
                      {student.externalId || student.studentKey.slice(0, 8)}
                    </td>
                    <td>
                      <Link
                        className="panel-link"
                        href={`/students/${student.id}`}
                      >
                        View profile ↗
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Workspace>
  );
}
