#!/bin/sh
set -e

echo "=================================================="
echo " Starting Smart Calendar Scheduler Microservice"
echo " Port: 5000"
echo " Endpoints: GET /health, POST /api/schedule"
echo "=================================================="

exec uvicorn src.main:app --host 0.0.0.0 --port 5000 --log-level info
