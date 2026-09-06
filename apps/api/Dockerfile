# syntax=docker/dockerfile:1
#
# Build context is the MONOREPO ROOT (see docker-compose.yml:
# build.context: . / build.dockerfile: apps/api/Dockerfile), because Prisma's
# schema lives in packages/db and Docker cannot COPY from outside its context.
FROM node:20-alpine AS base
WORKDIR /app

FROM base AS deps
COPY apps/api/package.json apps/api/package-lock.json* ./
RUN npm install --omit=dev

FROM base AS runtime
ENV NODE_ENV=production
COPY --from=deps /app/node_modules ./node_modules
COPY apps/api/package.json ./
COPY apps/api/src ./src
COPY packages/db/prisma ./prisma
RUN npx prisma generate

# Runs as a non-root user; the image should never need write access outside
# /tmp and whatever the CSV-upload storage mount provides.
RUN addgroup -S edutrace && adduser -S edutrace -G edutrace
USER edutrace

EXPOSE 4000
CMD ["npm", "start"]
