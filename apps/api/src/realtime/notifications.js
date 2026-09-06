import Redis from "ioredis";

import { env } from "../config/env.js";

const publisher = new Redis(env.REDIS_URL, {
  lazyConnect: true,
  maxRetriesPerRequest: 1,
});

export async function publishNotification(schoolId, payload) {
  if (!schoolId) return;
  try {
    if (publisher.status === "wait") await publisher.connect();
    await publisher.publish(
      `edutrace:notifications:${schoolId}`,
      JSON.stringify(payload),
    );
  } catch {
    // Real-time delivery is best effort; persisted reports remain authoritative.
  }
}

export async function subscribeToNotifications(schoolId, onMessage) {
  const subscriber = publisher.duplicate();
  await subscriber.subscribe(`edutrace:notifications:${schoolId}`);
  subscriber.on("message", (_channel, message) => {
    try {
      onMessage(JSON.parse(message));
    } catch {
      // Ignore malformed internal messages.
    }
  });
  return async () => {
    try {
      await subscriber.unsubscribe(`edutrace:notifications:${schoolId}`);
    } finally {
      subscriber.disconnect();
    }
  };
}
