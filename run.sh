#!/bin/sh
set -e

echo "==================================="
echo " Smart Calendar Scheduler Starting"
echo " Port: 5000"
echo "==================================="

# venv binaries are in PATH via Dockerfile ENV
exec uvicorn src.main:app --host 0.0.0.0 --port 5000 --log-level info
