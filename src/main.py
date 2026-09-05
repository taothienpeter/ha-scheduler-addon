import os
import time
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .models.schemas import ScheduleRequest, ScheduleResponse
from .core.engine import run_smart_scheduler_pipeline

app = FastAPI(
    title="Smart Calendar Scheduler API",
    description="Production-grade AI scheduling engine for Home Assistant (HAOS) & n8n integration",
    version="1.1.0"
)

# Enable CORS for local and Home Assistant integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def get_dashboard():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Smart Calendar Scheduler API is running. Dashboard static files not found."}

@app.get("/health")
def health_check() -> Dict[str, str]:
    return {
        "status": "ok",
        "service": "Smart Calendar Scheduler",
        "version": "1.1.0"
    }

@app.get("/api/presets")
def get_presets() -> Dict[str, Any]:
    return {
        "standard_workday": {
            "title": "Workday Tiêu Chuẩn (Standard Workday)",
            "description": "3 task lập trình & viết tài liệu xen kẽ các cuộc họp cố định và giờ ăn trưa.",
            "payload": {
                "current_time": "2026-09-05T08:00:00",
                "userPreferences": {
                    "working_hours": [480, 1080],
                    "buffer_time": 10,
                    "frozenZoneHours": 2
                },
                "fixedEvents": [
                    {
                        "id": "fe_standup",
                        "name": "Họp Daily Standup",
                        "startTime": "2026-09-05T09:00:00",
                        "endTime": "2026-09-05T09:30:00",
                        "is_busy": True
                    },
                    {
                        "id": "fe_lunch",
                        "name": "Nghỉ trưa & Ăn cơm",
                        "startTime": "2026-09-05T12:00:00",
                        "endTime": "2026-09-05T13:00:00",
                        "is_busy": True
                    },
                    {
                        "id": "fe_client",
                        "name": "Đồng bộ Khách hàng (Client Sync)",
                        "startTime": "2026-09-05T15:30:00",
                        "endTime": "2026-09-05T16:30:00",
                        "is_busy": True
                    }
                ],
                "tasks": [
                    {
                        "id": "t_backend",
                        "name": "Lập trình Backend Architecture",
                        "estimated_effort": 90,
                        "priority": 5,
                        "contextType": "coding",
                        "deadline": "2026-09-05T18:00:00"
                    },
                    {
                        "id": "t_doc",
                        "name": "Viết Tài liệu API & Tích hợp",
                        "estimated_effort": 60,
                        "priority": 3,
                        "contextType": "writing",
                        "deadline": "2026-09-05T18:00:00"
                    },
                    {
                        "id": "t_admin",
                        "name": "Xử lý Email & Duyệt chi phí",
                        "estimated_effort": 45,
                        "priority": 2,
                        "contextType": "admin",
                        "deadline": "2026-09-05T19:00:00"
                    }
                ]
            }
        },
        "starvation_deadline": {
            "title": "Áp Lực Deadline & Starvation Aging",
            "description": "1 task Hotfix deadline gấp và 1 task bị dời nhiều lần (Starvation aging) tự động nâng độ ưu tiên.",
            "payload": {
                "current_time": "2026-09-05T08:00:00",
                "userPreferences": {
                    "working_hours": [480, 1080],
                    "buffer_time": 10,
                    "maxDeferralThreshold": 3
                },
                "fixedEvents": [
                    {
                        "id": "fe_review",
                        "name": "Họp Chiến Lược Q3",
                        "startTime": "2026-09-05T09:30:00",
                        "endTime": "2026-09-05T11:30:00",
                        "is_busy": True
                    },
                    {
                        "id": "fe_lunch2",
                        "name": "Nghỉ trưa",
                        "startTime": "2026-09-05T12:00:00",
                        "endTime": "2026-09-05T13:00:00",
                        "is_busy": True
                    }
                ],
                "tasks": [
                    {
                        "id": "t_hotfix",
                        "name": "Sửa lỗi bảo mật Hotfix (Deadline Gấp)",
                        "estimated_effort": 60,
                        "priority": 5,
                        "contextType": "coding",
                        "deadline": "2026-09-05T13:30:00"
                    },
                    {
                        "id": "t_starved",
                        "name": "Báo cáo kiểm toán (Bị hoãn 4 lần)",
                        "estimated_effort": 45,
                        "priority": 2,
                        "contextType": "admin",
                        "deferral_count": 4,
                        "deadline": "2026-09-06T18:00:00"
                    },
                    {
                        "id": "t_routine",
                        "name": "Dọn dẹp mã nguồn & Refactor",
                        "estimated_effort": 60,
                        "priority": 2,
                        "contextType": "coding",
                        "deadline": "2026-09-07T18:00:00"
                    }
                ]
            }
        },
        "task_spanning": {
            "title": "Task Lớn Chia Nhỏ (Spanning 3 Giờ)",
            "description": "Task nghiên cứu 180 phút được thuật toán tự động băm nhỏ thành các phiên 90m + 60m + 30m khớp theo nhịp năng lượng cao.",
            "payload": {
                "current_time": "2026-09-05T08:00:00",
                "userPreferences": {
                    "working_hours": [480, 1080],
                    "buffer_time": 10
                },
                "fixedEvents": [
                    {
                        "id": "fe_1on1",
                        "name": "Họp 1-on-1 Quản Lý",
                        "startTime": "2026-09-05T10:00:00",
                        "endTime": "2026-09-05T11:00:00",
                        "is_busy": True
                    },
                    {
                        "id": "fe_lunch3",
                        "name": "Nghỉ trưa",
                        "startTime": "2026-09-05T12:30:00",
                        "endTime": "2026-09-05T13:30:00",
                        "is_busy": True
                    },
                    {
                        "id": "fe_allhands",
                        "name": "All-Hands Toàn Công Ty",
                        "startTime": "2026-09-05T15:30:00",
                        "endTime": "2026-09-05T16:30:00",
                        "is_busy": True
                    }
                ],
                "tasks": [
                    {
                        "id": "t_ml",
                        "name": "Huấn luyện Mô hình AI (3 Giờ)",
                        "estimated_effort": 180,
                        "priority": 5,
                        "contextType": "coding",
                        "deadline": "2026-09-05T18:30:00"
                    },
                    {
                        "id": "t_pr",
                        "name": "Review Code Pull Requests",
                        "estimated_effort": 45,
                        "priority": 3,
                        "contextType": "coding",
                        "deadline": "2026-09-05T18:00:00"
                    }
                ]
            }
        }
    }

from datetime import datetime
from fastapi import Request

latest_execution_record: Optional[Dict[str, Any]] = None

@app.get("/api/latest-execution")
def get_latest_execution() -> Dict[str, Any]:
    if not latest_execution_record:
        return {
            "status": "empty",
            "message": "Chưa có request nào từ n8n được ghi nhận kể từ khi khởi động."
        }
    return {
        "status": "ok",
        "data": latest_execution_record
    }

@app.post("/api/schedule", response_model=ScheduleResponse)
def schedule_tasks(request: ScheduleRequest, raw_req: Request) -> ScheduleResponse:
    try:
        start_time = time.time()
        client_ip = raw_req.client.host if raw_req.client else "unknown"
        response = run_smart_scheduler_pipeline(request)
        elapsed = time.time() - start_time
        response.message = f"Optimized in {elapsed:.3f}s"

        global latest_execution_record
        latest_execution_record = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "client_ip": client_ip,
            "elapsed_seconds": round(elapsed, 3),
            "request": request.model_dump(),
            "response": response.model_dump()
        }

        return response
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"SchedulerInternalError: {str(e)}")
