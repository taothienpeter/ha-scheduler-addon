#!/usr/bin/with-contenv bashio

# Activate virtual environment
export PATH="/opt/venv/bin:$PATH"

LOG_LEVEL=$(bashio::config 'log_level' 'info')

bashio::log.info "Starting Smart Calendar Scheduler..."
bashio::log.info "Port: 5000 | Log level: ${LOG_LEVEL}"

exec uvicorn src.main:app \
    --host 0.0.0.0 \
    --port 5000 \
    --log-level "${LOG_LEVEL}" \
    --app-dir /app
