#!/command/with-contenv bashio

echo "Starting Smart Calendar Scheduler API..."
uvicorn src.main:app --host 0.0.0.0 --port 5000 --log-level info
