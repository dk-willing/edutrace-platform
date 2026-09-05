const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";
let accessToken = "";
let currentTeacher = null;

export function setAccessToken(token) {
  accessToken = token;
  if (typeof window !== "undefined")
    window.sessionStorage.setItem("edutrace_access_token", token);
}

export function getAccessToken() {
  if (!accessToken && typeof window !== "undefined")
    accessToken = window.sessionStorage.getItem("edutrace_access_token") || "";
  return accessToken;
}

export function setCurrentTeacher(teacher) {
  currentTeacher = teacher;
  if (typeof window !== "undefined")
    window.sessionStorage.setItem("edutrace_teacher", JSON.stringify(teacher));
}

export function getCurrentTeacher() {
  if (!currentTeacher && typeof window !== "undefined") {
    const stored = window.sessionStorage.getItem("edutrace_teacher");
    currentTeacher = stored ? JSON.parse(stored) : null;
  }
  return currentTeacher;
}

export function clearAccessToken() {
  accessToken = "";
  currentTeacher = null;
  if (typeof window !== "undefined") {
    window.sessionStorage.removeItem("edutrace_access_token");
    window.sessionStorage.removeItem("edutrace_teacher");
  }
}

export async function apiRequest(path, options = {}) {
  let response;
  const token = getAccessToken();
  const isFormData =
    typeof FormData !== "undefined" && options.body instanceof FormData;
  try {
    response = await fetch(`${apiBase}${path}`, {
      credentials: "include",
      headers: {
        ...(isFormData ? {} : { "Content-Type": "application/json" }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers || {}),
      },
      ...options,
      body: options.body
        ? isFormData
          ? options.body
          : JSON.stringify(options.body)
        : undefined,
    });
  } catch (error) {
    throw new Error(
      `Could not reach the EduTrace API at ${apiBase}. ${error.message}`,
    );
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const details = Array.isArray(payload.error?.details)
      ? payload.error.details
          .map(
            (detail) =>
              `${detail.path?.join(".") || "Field"}: ${detail.message}`,
          )
          .join("; ")
      : "";
    const message =
      [payload.error?.message, details].filter(Boolean).join(" ") ||
      "The request could not be completed.";
    const error = new Error(message);
    error.code = payload.error?.code;
    error.details = payload.error?.details;
    throw error;
  }
  return payload;
}
