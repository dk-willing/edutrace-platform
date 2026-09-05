import jwt from "jsonwebtoken";

import { env } from "../../config/env.js";
import {
  ForbiddenError,
  UnauthorizedError,
} from "../../middleware/errorHandler.js";
import { prisma } from "../../db/prisma.js";
import { publicTeacher } from "./auth.service.js";

export async function requireAuth(req, _res, next) {
  try {
    const header = req.get("authorization");
    if (!header?.startsWith("Bearer "))
      throw new UnauthorizedError("Authentication is required.");
    const payload = jwt.verify(header.slice(7), env.JWT_ACCESS_SECRET);
    const teacher = await prisma.teacher.findUnique({
      where: { id: payload.sub },
      include: { school: true },
    });
    if (!teacher || teacher.status !== "ACTIVE")
      throw new UnauthorizedError("Authentication is required.");
    req.auth = {
      teacher: publicTeacher(teacher),
      teacherId: teacher.id,
      schoolId: teacher.schoolId,
      role: teacher.role,
    };
    return next();
  } catch (error) {
    if (error instanceof UnauthorizedError) return next(error);
    return next(new UnauthorizedError("Authentication is required."));
  }
}

export function requireRole(...roles) {
  return (req, _res, next) => {
    if (!req.auth || !roles.includes(req.auth.role)) {
      return next(
        new ForbiddenError(
          "You do not have permission to perform this action.",
        ),
      );
    }
    return next();
  };
}
