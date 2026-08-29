#!/bin/sh
set -e

echo "=================================================="
echo " Smart Calendar Scheduler - Starting..."
echo " FastAPI port 5000"
echo "=================================================="

exec python3 -m uvicorn src.main:app --host 0.0.0.0 --port 5000 --log-level info
