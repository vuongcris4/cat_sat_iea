# ============================================
# Cat Sat IEA - Production Docker Image
# Django + Daphne (ASGI) + Redis Channels
# ============================================

FROM python:3.11-slim

# Environment
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=iea_project.settings

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir whitenoise

# Copy source code
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

# Create data directories with proper permissions
RUN mkdir -p /app/patterns_cache /app/data

# Non-root user - create and set ownership AFTER directories
RUN adduser --disabled-password --gecos '' appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Run with Daphne (ASGI for WebSocket)
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "--application-close-timeout", "300", "iea_project.asgi:application"]
