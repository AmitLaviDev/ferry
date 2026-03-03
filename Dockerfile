# syntax=docker/dockerfile:1

# --- Stage 1: Build dependencies ---
FROM ghcr.io/astral-sh/uv:0.10 AS uv
FROM public.ecr.aws/lambda/python:3.14 AS builder

COPY --from=uv /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1
ENV UV_NO_INSTALLER_METADATA=1

WORKDIR /build

# Copy workspace root files for dependency resolution
COPY pyproject.toml uv.lock /build/
COPY utils/pyproject.toml /build/utils/
COPY backend/pyproject.toml /build/backend/

# Install third-party dependencies (cached separately from workspace changes)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-emit-workspace --no-dev --package ferry-backend \
      -o requirements.txt && \
    uv pip install --no-cache-dir -r requirements.txt \
      --target /build/deps

# Copy workspace source and install workspace members
COPY utils/src /build/utils/src
COPY backend/src /build/backend/src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-dev --no-editable --package ferry-backend \
      -o requirements-all.txt && \
    uv pip install --no-cache-dir -r requirements-all.txt \
      --target /build/all

# --- Stage 2: Runtime ---
FROM public.ecr.aws/lambda/python:3.14

# Copy all dependencies (third-party + workspace members)
COPY --from=builder /build/all ${LAMBDA_TASK_ROOT}

CMD ["ferry_backend.webhook.handler.handler"]
