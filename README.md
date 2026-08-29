# Smart Calendar Scheduler — Home Assistant OS (HAOS) Add-on

Hệ thống lập lịch thông minh thế hệ mới (Smart Schedule Engine) dành cho Home Assistant và n8n.

---

## 🌟 Tính Năng Nổi Bật

- **Kiến trúc 5 Tầng Tối Ưu Hóa:**
  1. **Tier A (Understand & Hard Constraints):** Tính toán Planning Horizon nhiều ngày, trích xuất Free Slots, và kiểm tra 100% ràng buộc cứng (tránh trùng lịch, bảo vệ deadline, giải quyết phụ thuộc task).
  2. **Tier B (Decide & Urgency):** Tính độ khẩn cấp động (Dynamic Urgency) theo thời gian thực + Cơ chế chống bỏ đói công việc (Starvation Aging Policy).
  3. **Tier C (Generate & Strategy):** Cắt phiên linh hoạt (Flexible Sessions: 120, 90, 60, 45, 30 phút) và sinh kịch bản chiến lược (Batch vs Interleave).
  4. **Tier D (Optimize & Repair):** Động cơ sửa chữa lịch trình (`tryMove`, `trySwap`, `tryShrink`) + Thuật toán tìm kiếm cục bộ (Limited Local Search 2-Opt) + Hàng rào ổn định (Time Fencing & Schedule Nervousness Guard).
  5. **Tier E (Commit & Explainable AI):** Chia nhỏ công việc qua nhiều ngày (Stateful Spanning), học bù trừ ước lượng thời gian (Estimation Bias Learner), và xuất báo cáo minh bạch (XAI Report).

---

## 🚀 Cấu Trúc Thư Mục

```text
ha-scheduler-addon/
├── addon.yaml            # Cấu hình Metadata cho Home Assistant Add-on
├── config.yaml           # Cấu hình tham số môi trường
├── Dockerfile            # Docker alpine python 3.10
├── run.sh                # Script khởi động Uvicorn
├── requirements.txt      # FastAPI, Uvicorn, Pydantic
├── src/
│   ├── main.py           # FastAPI Server & CORS Middleware
│   ├── models/
│   │   └── schemas.py    # Pydantic Schemas & DTO
│   └── core/
│       ├── constraints.py# Horizon, Free Slots, Hard Constraints Validation
│       ├── urgency.py    # Dynamic Urgency, Aging, Strategy Buckets
│       ├── generation.py # Flexible Chunking & Scenario Generator
│       ├── evaluator.py  # Global Objective Scoring J
│       ├── repair.py     # Repair Engine Operators (Move, Swap, Shrink)
│       ├── local_search.py# Hill Climbing 2-Opt, Stability Guard, Time Fencing
│       ├── spanning.py   # Stateful Spanning, Bias Learner, XAI Report
│       └── engine.py     # Master Pipeline Orchestrator
└── tests/
    └── test_scheduler.py # Unit tests kiểm thử toàn diện
```

---

## 🔌 API Endpoints

### 1. Health Check
`GET /health`
```json
{
  "status": "ok",
  "service": "Smart Calendar Scheduler",
  "version": "1.0.0"
}
```

### 2. Schedule Optimization
`POST /api/schedule`

#### Request Body mẫu:
```json
{
  "tasks": [
    {
      "id": "task_1",
      "name": "Viết Báo Cáo Tài Chính",
      "estimated_effort": 150,
      "remaining_effort": 150,
      "contextType": "writing",
      "priority": 1,
      "deadline": "2026-08-30T17:00:00Z"
    },
    {
      "id": "task_2",
      "name": "Code Tính Năng Mới",
      "estimated_effort": 90,
      "contextType": "coding",
      "priority": 2
    }
  ],
  "fixedEvents": [
    {
      "id": "event_1",
      "name": "Họp Ban Giám Đốc",
      "startTime": "2026-08-29T10:00:00Z",
      "endTime": "2026-08-29T11:30:00Z",
      "is_busy": true
    }
  ],
  "userPreferences": {
    "working_hours": [540, 1020],
    "buffer_time": 15,
    "rescheduleThreshold": 0.10
  }
}
```

#### Response Body mẫu:
```json
{
  "success": true,
  "sessions": [
    {
      "sessionId": "sess_task_1_1",
      "taskId": "task_1",
      "taskName": "Viết Báo Cáo Tài Chính",
      "startTime": "2026-08-29T09:00:00+00:00",
      "endTime": "2026-08-29T09:45:00+00:00",
      "duration": 45,
      "contextType": "writing"
    }
  ],
  "updatedTasks": [
    {
      "id": "task_1",
      "name": "Viết Báo Cáo Tài Chính",
      "status": "PARTIAL",
      "remaining_effort": 105,
      "completed_effort": 45,
      "isSpanning": true
    }
  ],
  "score": 450.5,
  "scoreBreakdown": {
    "completedWorkScore": 240.0,
    "tardinessPenalty": 0.0,
    "switchingCostPenalty": 0.0,
    "fragmentationPenalty": 0.0,
    "overloadPenalty": 0.0,
    "userPreferenceBonus": 35.0,
    "finalScore": 275.0
  },
  "xaiReport": {
    "summary": {
      "totalTasks": 2,
      "completedCount": 1,
      "partialCount": 1,
      "deferredCount": 0,
      "totalScheduledHours": 2.5
    },
    "taskExplanations": [...],
    "insightsAndTips": [...]
  },
  "message": "Optimized in 0.025s"
}
```

---

## 🛠️ Triển khai lên Home Assistant (HAOS)

1. Đẩy thư mục này lên GitHub Repository riêng (ví dụ: `ha-addons/smart_calendar_scheduler`).
2. Mở Home Assistant $\rightarrow$ **Settings** $\rightarrow$ **Add-ons** $\rightarrow$ **Add-on Store**.
3. Chọn menu 3 chấm (Góc phải) $\rightarrow$ **Repositories** $\rightarrow$ Dán URL GitHub của bạn vào.
4. Tìm và bấm **Install** Add-on "Smart Calendar Scheduler".
5. Bật **Start on boot** và bấm **Start**.

---

## 🔄 Cấu hình n8n Workflow

1. Trong n8n, tạo node **Google Calendar** / **Notion** để lấy Tasks và Events.
2. Dùng node **HTTP Request**:
   - Method: `POST`
   - URL: `http://smart_calendar_scheduler:5000/api/schedule` (hoặc IP của Home Assistant).
   - Body: JSON dữ liệu từ Calendar và Notion.
3. Nhận kết quả:
   - Dùng node **Google Calendar** tạo mới sự kiện từ mảng `sessions`.
   - Dùng node **Notion** cập nhật trạng thái `updatedTasks`.
   - Dùng node **Telegram** gửi báo cáo `xaiReport` cho bạn mỗi sáng.
