import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta

from src.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_schedule_endpoint_empty():
    now = datetime.now()
    req_data = {
        "tasks": [],
        "fixedEvents": [],
        "userPreferences": {
            "working_hours": [540, 1020],
            "buffer_time": 15
        },
        "current_time": now.isoformat()
    }
    
    response = client.post("/api/schedule", json=req_data)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["sessions"]) == 0

def test_schedule_endpoint_valid_task():
    now = datetime.now()
    req_data = {
        "tasks": [
            {
                "id": "t1",
                "name": "API Task",
                "estimated_effort": 60,
                "deadline": (now + timedelta(days=2)).isoformat()
            }
        ],
        "fixedEvents": [],
        "userPreferences": {
            "working_hours": [0, 1439], # 24/7 to guarantee slot
            "buffer_time": 0
        },
        "current_time": now.isoformat()
    }
    
    response = client.post("/api/schedule", json=req_data)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["sessions"]) > 0
    assert data["sessions"][0]["taskId"] == "t1"
    assert data["sessions"][0]["duration"] == 60
