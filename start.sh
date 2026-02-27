#!/bin/sh

echo "Running database migrations..."

# Capture output and exit code without set -e (we check the exit code ourselves)
UPGRADE_OUTPUT=$(alembic upgrade head 2>&1)
UPGRADE_EXIT=$?

echo "$UPGRADE_OUTPUT"

if [ $UPGRADE_EXIT -ne 0 ]; then
    if echo "$UPGRADE_OUTPUT" | grep -q "already exists"; then
        echo "Tables already exist from initial create_all — stamping alembic to head..."
        alembic stamp head
    else
        echo "Migration failed, aborting startup."
        exit 1
    fi
fi

echo "Starting application..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
