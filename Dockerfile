# Multi-stage Dockerfile for fastapi-red
# Stage 1: Build & wheels preparation
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies if needed
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Lean runtime container
FROM python:3.12-slim AS runner

WORKDIR /app

# Ensure python output is streamed directly to logs
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PATH=/root/.local/bin:$PATH

# Copy installed Python packages from builder stage
COPY --from=builder /root/.local /root/.local

# Copy application directories
COPY src/ /app/src/
COPY static/ /app/static/
COPY dist/ /app/dist/
COPY nodes/ /app/nodes/
COPY storage/ /app/storage/
COPY pyproject.toml /app/

# Expose standard FastAPI-Red / Node-RED HTTP port
EXPOSE 8080

# Default storage volume mount point
VOLUME ["/app/storage"]

# Start uvicorn server serving fastapi-red
CMD ["uvicorn", "fastapi_red.main:app", "--host", "0.0.0.0", "--port", "8080"]

