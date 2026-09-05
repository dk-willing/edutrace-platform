# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
WORKDIR /app

# xgboost/scikit-learn need a C++ runtime at import time even from a wheel.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY vendor/pyproject.toml vendor/pyproject.toml
COPY vendor/edutrace vendor/edutrace
RUN pip install --no-cache-dir ./vendor

COPY vendor/artifacts vendor/artifacts
COPY app app

RUN addgroup --system edutrace && adduser --system --ingroup edutrace edutrace
# Model artifacts and audit log path must stay writable if EDUTRACE_AUDIT_PATH
# points inside the image; in production this should be a mounted volume or
# object storage, not image-local disk (see STATUS.md's own note on this).
RUN mkdir -p /app/audit && chown -R edutrace:edutrace /app
USER edutrace

ENV EDUTRACE_MODEL_DIR=/app/vendor/artifacts/model
ENV EDUTRACE_AUDIT_PATH=/app/audit/audit.jsonl
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
