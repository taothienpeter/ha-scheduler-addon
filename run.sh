#!/bin/sh
set -e

# Activate the virtual environment created in Dockerfile
export PATH="/opt/venv/bin:$PATH"

echo "=================================================="
echo " Smart Calendar Scheduler v1.1.0 Starting"
echo " Listening on http://0.0.0.0:5000"
echo " Endpoints: GET / (Dashboard) | GET /health | POST /api/schedule"
echo "=================================================="

exec uvicorn src.main:app \
    --host 0.0.0.0 \
    --port 5000 \
    --log-level info
