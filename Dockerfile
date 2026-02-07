# ---- Stage 1: Build frontend ----
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python backend ----
FROM python:3.12-slim AS runtime

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy backend and install dependencies
COPY backend/pyproject.toml backend/uv.lock* ./backend/
WORKDIR /app/backend
RUN uv sync --no-dev --no-editable

# Copy backend source
COPY backend/app ./app
COPY backend/run.py ./

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist

# Create required directories
RUN mkdir -p /app/.claude/heartbeats /app/.claude/signals /app/tasks /app/logs

# Default environment
ENV LU_HOST=0.0.0.0
ENV LU_PORT=8000
ENV LU_DB_PATH=/app/data/latent.db
ENV LU_LOG_LEVEL=info

# Persistent data volume
VOLUME /app/data

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
