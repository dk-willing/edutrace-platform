"use client";

import { useEffect, useState } from "react";
import { Workspace } from "../dashboard/Workspace";
import { apiUrl, getAccessToken } from "../lib/api";

export default function NotificationsPage() {
  const [notifications, setNotifications] = useState([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    let buffer = "";
    async function connect() {
      try {
        const response = await fetch(apiUrl("/api/v1/notifications/stream"), {
          signal: controller.signal,
          headers: { Authorization: `Bearer ${getAccessToken()}` },
        });
        if (!response.ok || !response.body || controller.signal.aborted) return;
        setConnected(true);
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        while (!controller.signal.aborted) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const events = buffer.split("\n\n");
          buffer = events.pop() || "";
          for (const event of events) {
            const dataLine = event
              .split("\n")
              .find((line) => line.startsWith("data: "));
            if (!dataLine) continue;
            try {
              setNotifications((current) =>
                [JSON.parse(dataLine.slice(6)), ...current].slice(0, 50),
              );
            } catch {
              // Ignore malformed event data.
            }
          }
        }
      } catch (error) {
        if (error?.name !== "AbortError" && !controller.signal.aborted) {
          setConnected(false);
        }
      } finally {
        setConnected(false);
      }
    }
    connect();
    return () => {
      if (!controller.signal.aborted) controller.abort();
    };
  }, []);

  return (
    <Workspace
      title="Tasks & notifications"
      subtitle="Live support alerts for your school"
    >
      <div className="notice" role="status">
        {connected
          ? "Live notifications connected."
          : "Connecting to live notifications..."}
      </div>
      <section className="panel">
        {!notifications.length ? (
          <div className="empty-state compact">
            <h3>No new notifications</h3>
            <p>Urgent support alerts will appear here as analysis completes.</p>
          </div>
        ) : (
          notifications.map((notification, index) => (
            <div className="task" key={`${notification.createdAt}-${index}`}>
              <span
                className="task-dot"
                style={{ background: "var(--coral)" }}
              />
              <div>
                <p>
                  {notification.message ||
                    "A new support notification is available."}
                </p>
                <small>
                  {new Date(notification.createdAt).toLocaleString()}
                </small>
              </div>
            </div>
          ))
        )}
      </section>
    </Workspace>
  );
}
