#!/bin/bash
set -e

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
while ! python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('${DB_HOST:-postgres}', ${DB_PORT:-5432})); s.close()" 2>/dev/null; do
    echo "PostgreSQL not ready, retrying in 2s..."
    sleep 2
done
echo "PostgreSQL is ready!"

# Run migrations
echo "Running migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Start Daphne
echo "Starting Daphne ASGI server..."
exec daphne -b 0.0.0.0 -p 8000 --application-close-timeout 300 iea_project.asgi:application
