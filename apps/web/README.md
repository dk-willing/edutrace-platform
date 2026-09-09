# EduTrace web

The Next.js App Router frontend includes the public product site, teacher
registration and login, privacy and terms routes, and a responsive workspace
covering the dashboard, classes, students, student profile, imports, reports,
notifications, and settings.

The auth forms call the Node API at `NEXT_PUBLIC_API_URL` and keep the access
token in memory. Refresh sessions remain in the API's HttpOnly cookie. The
workspace uses the school, student, import, and reporting endpoints provided by
the Node API.
