import time
from typing import Dict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .models.schemas import ScheduleRequest, ScheduleResponse
from .core.engine import run_smart_scheduler_pipeline

app = FastAPI(
    title="Smart Calendar Scheduler API",
    description="Production-grade AI scheduling engine for Home Assistant (HAOS) & n8n integration",
    version="1.0.0"
)

# Enable CORS for local and Home Assistant integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check() -> Dict[str, str]:
    return {
        "status": "ok",
        "service": "Smart Calendar Scheduler",
        "version": "1.0.0"
    }

@app.post("/api/schedule", response_model=ScheduleResponse)
def schedule_tasks(request: ScheduleRequest) -> ScheduleResponse:
    try:
        start_time = time.time()
        response = run_smart_scheduler_pipeline(request)
        elapsed = time.time() - start_time
        response.message = f"Optimized in {elapsed:.3f}s"
        return response
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"SchedulerInternalError: {str(e)}")
