import pytest
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_dashboard_endpoint_html():
    """Kiểm tra endpoint GET / phục vụ HTML giao diện Dashboard"""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "Smart Calendar Scheduler" in response.text
    assert "Gantt Timeline" in response.text

def test_static_assets_served():
    """Kiểm tra các tệp tĩnh CSS và JS phục vụ đúng định dạng"""
    css_res = client.get("/static/style.css")
    assert css_res.status_code == 200
    assert "text/css" in css_res.headers.get("content-type", "")

    js_res = client.get("/static/app.js")
    assert js_res.status_code == 200
    assert "javascript" in js_res.headers.get("content-type", "")

def test_presets_endpoint():
    """Kiểm tra endpoint GET /api/presets trả về đủ 3 kịch bản thực tế"""
    response = client.get("/api/presets")
    assert response.status_code == 200
    data = response.json()
    assert "standard_workday" in data
    assert "starvation_deadline" in data
    assert "task_spanning" in data
    
    workday = data["standard_workday"]
    assert "tasks" in workday["payload"]
    assert len(workday["payload"]["tasks"]) >= 3

def test_schedule_pipeline_trace():
    """Kiểm tra POST /api/schedule trả về telemetry pipelineTrace"""
    payload = {
        "current_time": "2026-09-05T08:00:00",
        "tasks": [
            {
                "id": "t1",
                "name": "Quick Fix",
                "estimated_effort": 60,
                "priority": 5,
                "contextType": "coding"
            }
        ],
        "fixedEvents": [],
        "userPreferences": {
            "working_hours": [480, 1020],
            "buffer_time": 10
        }
    }
    response = client.post("/api/schedule", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "pipelineTrace" in data
    trace = data["pipelineTrace"]
    assert trace is not None
    assert trace["freeSlotsCount"] >= 1
    assert "strategyBuckets" in trace
    assert trace["elapsedSeconds"] >= 0.0
