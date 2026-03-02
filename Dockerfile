# ============================================
# Cat Sat IEA - Production Docker Image
# Django + Daphne (ASGI) + PostgreSQL + Redis
# ============================================

FROM python:3.11-slim

# Environment
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=iea_project.settings

WORKDIR /app

# System dependencies (incl. libpq-dev for PostgreSQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Create data directories with proper permissions
RUN mkdir -p /app/patterns_cache /app/data /app/logs

# Non-root user
RUN adduser --disabled-password --gecos '' appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Use entrypoint script (waits for PG, migrates, starts Daphne)
ENTRYPOINT ["/app/entrypoint.sh"]
