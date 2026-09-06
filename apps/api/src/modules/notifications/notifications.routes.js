import { Router } from "express";

import { ForbiddenError } from "../../middleware/errorHandler.js";
import { subscribeToNotifications } from "../../realtime/notifications.js";
import { requireAuth } from "../auth/auth.middleware.js";

const router = Router();
router.use(requireAuth);

router.get("/stream", async (req, res, next) => {
  if (!req.auth.schoolId)
    return next(new ForbiddenError("Your account is not linked to a school."));
  res.status(200).set({
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache, no-store, must-revalidate",
    Connection: "keep-alive",
    "X-Accel-Buffering": "no",
  });
  res.flushHeaders();
  res.write(": connected\n\n");
  let unsubscribe;
  try {
    unsubscribe = await subscribeToNotifications(
      req.auth.schoolId,
      (payload) => {
        if (payload.teacherId && payload.teacherId !== req.auth.teacherId)
          return;
        res.write(`event: notification\ndata: ${JSON.stringify(payload)}\n\n`);
      },
    );
  } catch (error) {
    res.end();
    return next(error);
  }
  const heartbeat = setInterval(() => res.write(": heartbeat\n\n"), 25_000);
  req.on("close", async () => {
    clearInterval(heartbeat);
    await unsubscribe?.();
  });
});

export { router as notificationsRouter };
