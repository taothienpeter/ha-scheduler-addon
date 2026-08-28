# Smart Calendar Scheduler — Home Assistant Add-on

## 1. Giới thiệu (Overview)
Add-on này cung cấp một microservice chạy nền (FastAPI) để thực thi thuật toán xếp lịch cá nhân hóa (Smart Scheduling V3). 
Mục đích chính là hoạt động như một **Execution Engine** độc lập, nhận yêu cầu từ các workflow của **n8n** (hoặc AppDaemon/Home Assistant Automation), tính toán lịch trình tối ưu và trả về kết quả JSON.

---

## 2. Cách n8n kết nối và gọi API (n8n Integration)

Trong workflow của **n8n** (cũng chạy trên Home Assistant):

1. Thêm node **HTTP Request**.
2. Cấu hình các thông số sau:
   - **Method:** `POST`
   - **URL:** `http://localhost:5000/api/schedule` (hoặc `http://homeassistant.local:5000/api/schedule` nếu n8n ở máy khác)
   - **Send Body:** `true`
   - **Body Content Type:** `JSON`
   - **Specify Body:** `Using JSON`

---

## 3. Mẫu Dữ liệu Gửi đi từ n8n (Request Payload Example)

```json
{
  "tasks": [
    {
      "id": "task_1",
      "name": "Viết báo cáo kỹ thuật",
      "estimated_effort": 90,
      "priority": 2,
      "contextType": "writing",
      "preferredTime": "morning",
      "deadline": "2026-08-30T17:00:00+07:00"
    },
    {
      "id": "task_2",
      "name": "Fix bug backend",
      "estimated_effort": 120,
      "priority": 1,
      "contextType": "coding",
      "preferredTime": "afternoon"
    }
  ],
  "fixedEvents": [
    {
      "id": "meeting_1",
      "name": "Daily Scrum",
      "startTime": "2026-08-29T09:00:00+07:00",
      "endTime": "2026-08-29T09:30:00+07:00",
      "is_busy": true
    }
  ],
  "userPreferences": {
    "working_hours": [540, 1020],
    "buffer_time": 15,
    "weights": {
      "wCompleted": 1.0,
      "wTardiness": 2.5,
      "wSwitching": 15.0,
      "wFragmentation": 20.0,
      "wOverload": 1.5,
      "wPreference": 10.0
    }
  }
}
```

---

## 4. Dữ liệu Kết quả Trả về (Response Output)

```json
{
  "success": true,
  "sessions": [
    {
      "sessionId": "sess_task_1_1",
      "taskId": "task_1",
      "taskName": "Viết báo cáo kỹ thuật",
      "startTime": "2026-08-29T09:45:00+07:00",
      "endTime": "2026-08-29T11:15:00+07:00",
      "duration": 90,
      "contextType": "writing"
    }
  ],
  "updatedTasks": [
    {
      "id": "task_1",
      "name": "Viết báo cáo kỹ thuật",
      "status": "COMPLETED",
      "remaining_effort": 0
    }
  ],
  "score": 105.0,
  "scoreBreakdown": {
    "completedWorkScore": 90.0,
    "tardinessPenalty": 0.0,
    "switchingCostPenalty": 0.0,
    "fragmentationPenalty": 0.0,
    "overloadPenalty": 0.0,
    "userPreferenceBonus": 15.0,
    "finalScore": 105.0
  },
  "xaiReport": {
    "summary": {
      "totalTasks": 2,
      "completedCount": 1,
      "partialCount": 0,
      "deferredCount": 1,
      "totalScheduledHours": 1.5
    }
  },
  "message": "Optimization pipeline finished successfully."
}
```

---

## 5. Kiểm tra Trạng thái & Debug (Health Check & Logs)

- **Health Check Endpoint:** `GET http://localhost:5000/health` (trả về `{"status": "ok"}`).
- **Xem Logs:** Vào Home Assistant -> **Settings** -> **Add-ons** -> **Smart Calendar Scheduler** -> Tab **Log** để xem nhật ký chạy và xử lý lỗi.
