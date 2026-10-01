# Smart Calendar Scheduler — Tài Liệu Tích Hợp & API Reference

## 1. Giới thiệu (Overview)
Add-on này cung cấp một microservice chạy nền (FastAPI) để thực thi thuật toán xếp lịch cá nhân hóa đa mục tiêu (**Smart Scheduling Engine**). 
Mục đích chính là hoạt động như một **Execution Engine** độc lập, nhận yêu cầu từ workflow của **n8n**, AppDaemon hoặc Home Assistant Automation, tính toán lịch trình tối ưu và trả về kết quả JSON.

---

## 2. Cách n8n kết nối và gọi API (n8n Integration)

Trong workflow của **n8n** (cùng chạy trên Home Assistant hoặc máy ngoài):

1. Thêm node **HTTP Request**.
2. Cấu hình các thông số sau:
   - **Method:** `POST`
   - **URL:** `http://localhost:5000/api/schedule` (hoặc `http://<ha-ip>:5000/api/schedule` nếu n8n ở server khác)
   - **Send Body:** `true`
   - **Body Content Type:** `JSON`
   - **Specify Body:** `Using JSON`

---

## 3. Cấu trúc Dữ liệu Gửi đi (Request Payload)

Dưới đây là một ví dụ JSON đầy đủ với tất cả các trường có thể cấu hình:

```json
{
  "current_time": "2026-08-29T08:30:00+07:00",
  "tasks": [
    {
      "id": "task_1",
      "name": "Viết báo cáo kỹ thuật",
      "estimated_effort": 90,
      "remaining_effort": 90,
      "completed_effort": 0,
      "priority": 2,
      "contextType": "writing",
      "preferredTime": "morning",
      "deadline": "2026-08-30T17:00:00+07:00",
      "dependencies": [],
      "deferral_count": 0,
      "status": "UNSCHEDULED"
    },
    {
      "id": "task_2",
      "name": "Fix bug backend",
      "estimated_effort": 120,
      "remaining_effort": 120,
      "completed_effort": 0,
      "priority": 1,
      "contextType": "coding",
      "preferredTime": "afternoon",
      "deadline": null,
      "dependencies": ["task_1"],
      "deferral_count": 0,
      "status": "UNSCHEDULED"
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
    "timezone": "Asia/Ho_Chi_Minh",
    "working_hours": [540, 1020],
    "buffer_time": 15,
    "rescheduleThreshold": 0.10,
    "frozenZoneHours": 3,
    "maxDeferralThreshold": 3,
    "estimationBiasFactor": 1.15,
    "weights": {
      "wCompleted": 1.0,
      "wTardiness": 2.5,
      "wSwitching": 15.0,
      "wFragmentation": 20.0,
      "wOverload": 1.5,
      "wPreference": 10.0
    }
  },
  "oldSchedule": [],
  "recentFeedbackEvents": []
}
```

---

### 3.1. Giải thích chi tiết từng trường trong Request Body

#### A. Trường cấp cao (Root Object):
| Tên trường | Kiểu dữ liệu | Bắt buộc | Mặc định | Ý nghĩa & Quy chuẩn |
| :--- | :--- | :---: | :--- | :--- |
| **`current_time`** | `string` (ISO-8601) | **Không** | `datetime.now()` | **Mốc thời gian hiện tại để tính toán.**<br>• Dùng để giả lập hoặc test với dữ liệu lịch sử.<br>• Nếu bạn bỏ trống, hệ thống sẽ lấy thời gian thực của máy chủ lúc nhận request.<br>• *Lưu ý:* Nếu dữ liệu `deadline` hoặc `fixedEvents` của bạn ở ngày trong quá khứ so với thời điểm thực, hãy truyền `current_time` cùng ngày với dữ liệu đó để tránh bị lỗi quá hạn (`OVERDUE`). |
| **`tasks`** | `Array<Task>` | Có | `[]` | Danh sách các công việc cần thuật toán sắp xếp vào lịch. |
| **`fixedEvents`** | `Array<FixedEvent>`| Không | `[]` | Danh sách các sự kiện cố định không thể dời (cuộc họp, lịch Google Calendar, v.v.). |
| **`userPreferences`**| `Object` | Không | *Default settings* | Cấu hình thói quen và ràng buộc làm việc của người dùng. |
| **`oldSchedule`** | `Array<Session>` | Không | `null` | Lịch trình cũ đã lưu trước đó. Dùng để thuật toán so sánh tính ổn định (*Schedule Stability*) nhằm tránh đảo lộn lịch nếu lịch mới chỉ cải thiện nhẹ. |
| **`recentFeedbackEvents`**| `Array<Event>` | Không | `[]` | Lịch sử bấm hoàn thành thực tế của người dùng để thuật toán tự học bù trừ sai số ước lượng (*Adaptive Estimation Bias*). |

---

#### B. Chi tiết từng trường của một Task (`tasks[...]`):
| Trường | Kiểu | Bắt buộc | Mặc định | Ý nghĩa |
| :--- | :--- | :---: | :--- | :--- |
| **`id`** | `string` | **Có** | - | Định danh duy nhất của task (ID trong Todoist, Notion, hoặc HA Todo). |
| **`name`** | `string` | **Có** | - | Tên hiển thị của công việc. |
| **`estimated_effort`** | `int` | **Có** | - | Tổng thời lượng ước tính ban đầu (tính bằng **phút**, phải $> 0$). |
| **`remaining_effort`** | `int` | Không | `= estimated_effort` | Số phút còn lại cần xếp lịch. Khi task làm dở dang qua nhiều ngày (*PARTIAL*), trường này sẽ giảm dần. |
| **`completed_effort`** | `int` | Không | `0` | Số phút đã hoàn thành tích lũy ở các phiên trước đó. |
| **`priority`** | `int` | Không | `3` | Mức độ ưu tiên gốc của người dùng từ **1** (Cực kỳ khẩn cấp) đến **5** (Rất thấp). |
| **`deadline`** | `string` | Không | `null` | Hạn chót tuyệt đối theo chuỗi ISO-8601 kèm múi giờ (vd: `"2026-08-30T17:00:00+07:00"`). Thuật toán coi đây là **Hard Constraint** (không bao giờ xếp session sau deadline). |
| **`contextType`** | `string` | Không | `"general"` | Phân loại ngữ cảnh: `'coding'`, `'writing'`, `'reading'`, `'meeting'`, `'admin'`, `'creative'`, `'general'`. Thuật toán dùng để tính chi phí chuyển đổi ngữ cảnh (*Switching Cost*) và ghép với nhịp sinh học năng lượng (*Energy Profile*). |
| **`preferredTime`** | `string` | Không | `null` | Khung giờ vàng ưa thích: `'morning'`, `'afternoon'`, hoặc `'evening'`. |
| **`dependencies`** | `string[]` | Không | `[]` | Mảng chứa các `id` của task tiên quyết. Task này chỉ được phép bắt đầu sau khi các task trong mảng phụ thuộc đã xong 100%. |
| **`deferral_count`** | `int` | Không | `0` | Số chu kỳ task đã bị dời (*DEFERRED*). Thuật toán dùng số này để kích hoạt cơ chế chống bỏ đói việc tồn (*Starvation Aging*). |
| **`status`** | `string` | Không | `"UNSCHEDULED"` | Trạng thái hiện tại: `'UNSCHEDULED'`, `'SCHEDULED'`, `'PARTIAL'`, `'COMPLETED'`, `'DEFERRED'`, `'OVERDUE'`. |

---

#### C. Chi tiết Sự kiện Cố định (`fixedEvents[...]`):
| Trường | Kiểu | Bắt buộc | Ý nghĩa |
| :--- | :--- | :---: | :--- |
| **`id`** | `string` | Có | Mã duy nhất của sự kiện lịch. |
| **`name`** | `string` | Có | Tên sự kiện (vd: "Họp Ban Giám Đốc"). |
| **`startTime`** | `string` (ISO-8601) | Có | Thời điểm bắt đầu sự kiện. |
| **`endTime`** | `string` (ISO-8601) | Có | Thời điểm kết thúc sự kiện. |
| **`is_busy`** | `boolean` | Không (`true`) | Nếu `true`, khoảng thời gian này sẽ bị chặn (không thể xếp task vào). |

---

#### D. Chi tiết Cấu hình Người dùng (`userPreferences`):
| Trường | Kiểu | Mặc định | Ý nghĩa |
| :--- | :--- | :--- | :--- |
| **`timezone`** | `string` | `"Asia/Ho_Chi_Minh"` | Múi giờ chính của người dùng. |
| **`working_hours`** | `[int, int]` | `[540, 1020]` | Khung giờ làm việc tính bằng phút từ 0h. Mặc định `[540, 1020]` là **09:00 đến 17:00**. |
| **`buffer_time`** | `int` | `15` | Số phút nghỉ/đệm an toàn trước và sau mỗi cuộc họp cố định. |
| **`rescheduleThreshold`**| `float` | `0.10` | Ngưỡng cải thiện điểm số (10%) cần đạt để thay đổi lịch cũ, chống đổi lịch liên tục gây xáo trộn (*Schedule Nervousness*). |
| **`maxDeferralThreshold`**| `int` | `3` | Số lần bị dời tối đa trước khi task được gắn cờ báo động khẩn cấp (*Starvation Warning*). |
| **`estimationBiasFactor`** | `float` | `1.15` | Hệ số bù trừ ước tính thời lượng (AI tự động cập nhật qua `recentFeedbackEvents`). |
| **`weights`** | `object` | `{...}` | Trọng số phạt/thưởng của hàm mục tiêu toàn cục (Utility Function). |

---

#### E. Chi tiết Sự kiện Phản hồi Thực tế (`recentFeedbackEvents[...]`):

Trường `recentFeedbackEvents` là kênh **học hỏi thích ứng (Adaptive Learning Loop)** của thuật toán nhằm khắc phục hội chứng *Planning Fallacy* (con người có xu hướng ước lượng thời gian quá lạc quan).

##### Mẫu JSON:
```json
[
  {
    "eventType": "TASK_COMPLETED",
    "taskId": "task_1",
    "contextType": "writing",
    "scheduledDuration": 60,
    "actualDuration": 90,
    "timestamp": "2026-08-29T11:30:00+07:00"
  },
  {
    "eventType": "TASK_MOVED_BY_USER",
    "taskId": "task_2",
    "scheduledDuration": 60,
    "newUserStartTime": "2026-08-29T15:00:00+07:00"
  }
]
```

##### Bảng giải thích chi tiết:
| Trường | Kiểu | Bắt buộc | Ý nghĩa |
| :--- | :--- | :---: | :--- |
| **`eventType`** | `string` | **Có** | Loại sự kiện phản hồi:<br>• `'TASK_COMPLETED'`: Người dùng bấm hoàn thành một công việc.<br>• `'TASK_MOVED_BY_USER'`: Người dùng tự tay kéo dời phiên làm việc sang giờ khác trên giao diện. |
| **`taskId`** | `string` | **Có** | ID của công việc tương ứng. |
| **`contextType`** | `string` | Không | Ngữ cảnh của công việc (`'coding'`, `'writing'`, `'general'`). |
| **`scheduledDuration`** | `int` | **Có** | Thời lượng mà thuật toán đã phân bổ cho phiên làm việc đó (phút, $> 0$). |
| **`actualDuration`** | `int` | Không | Số phút **thực tế** mà người dùng mất để làm xong công việc. Dùng để tính tỷ lệ sai số $\text{ratio} = \frac{\text{actualDuration}}{\text{scheduledDuration}}$. |
| **`newUserStartTime`** | `string` (ISO) | Không | Mốc giờ mới do người dùng chủ động kéo dời đến (áp dụng cho `TASK_MOVED_BY_USER`). |
| **`timestamp`** | `string` (ISO) | Không | Thời điểm ghi nhận hành động hoàn thành. |

##### Thuật toán học hỏi như thế nào?
- Mỗi khi nhận danh sách này, thuật toán cập nhật `estimationBiasFactor` theo công thức **Exponential Moving Average (EMA)** với tốc độ học $\alpha = 0.15$:
  $$\text{factor}_{mới} = (1 - 0.15) \cdot \text{factor}_{cũ} + 0.15 \cdot \text{observed\_ratio}$$
- Nếu phát hiện bạn thường xuyên cần nhiều hơn 25% thời gian so với ước tính, hệ thống sẽ tự động bù đắp khoảng đệm và phát cảnh báo trong `xaiReport.insightsAndTips`.

##### Workflow thực tế trong n8n / Home Assistant:
1. Khi người dùng bấm hoàn thành task trên Home Assistant Todo hoặc Todoist, n8n tính $\text{actualDuration} = \text{thời điểm bấm Done} - \text{thời điểm bắt đầu session}$.
2. n8n lưu sự kiện này vào hàng đợi tạm (Queue/Datastore).
3. Ở lần xếp lịch tiếp theo (ví dụ sáng mai), n8n truyền mảng các sự kiện này vào `recentFeedbackEvents` rồi làm rỗng hàng đợi.

---

#### F. Chi tiết Lịch Cũ Kiểm tra Độ Ổn định (`oldSchedule[...]`):

Dùng để ngăn chặn hiện tượng **Lịch bị bồn chồn (Schedule Nervousness)** — tránh việc đảo lộn lịch của người dùng nếu lịch mới chỉ tối ưu hơn một chút ($< 10\%$).

- **Định dạng:** Nhận vào chính mảng `sessions` mà API đã trả về ở lần chạy trước.
- **Quy tắc:**
  - Nếu `oldSchedule` bị xung đột với các cuộc họp mới thêm vào (`fixedEvents`) hoặc có task quá hạn: Bắt buộc đổi sang lịch mới (`COMMITTED`).
  - Nếu `oldSchedule` vẫn hợp lệ và kịch bản mới không tốt hơn tối thiểu 10% (`rescheduleThreshold`): Thuật toán sẽ từ chối đổi lịch và trả về lịch cũ (`RETAINED`).

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
      "contextType": "writing",
      "preferredTime": "morning",
      "isFrozen": true
    }
  ],
  "updatedTasks": [
    {
      "id": "task_1",
      "name": "Viết báo cáo kỹ thuật",
      "status": "COMPLETED",
      "remaining_effort": 0,
      "completed_effort": 90,
      "lastScheduledDuration": 90,
      "deferral_count": 0,
      "effectiveUrgency": 120.5,
      "slack_minutes": 1815
    },
    {
      "id": "task_old",
      "name": "Task quá hạn từ tháng trước",
      "status": "OVERDUE",
      "remaining_effort": 120,
      "completed_effort": 0,
      "lastScheduledDuration": 0,
      "deferral_count": 1,
      "effectiveUrgency": 350.0,
      "slack_minutes": -43200
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
    "timestamp": "2026-08-29T08:30:00+07:00",
    "summary": {
      "totalTasks": 2,
      "completedCount": 1,
      "partialCount": 0,
      "deferredCount": 0,
      "overdueCount": 1,
      "totalScheduledHours": 1.5
    },
    "taskExplanations": [
      {
        "taskId": "task_1",
        "taskName": "Viết báo cáo kỹ thuật",
        "status": "COMPLETED",
        "scheduledDuration": 90,
        "remainingEffort": 0,
        "explanation": "Allocated all 90m into your highest productivity window for [writing].",
        "energyMatch": "Optimal (Peak focus at 9:00)",
        "urgencyFactor": "Urgency: 120.5",
        "conflictResolution": null
      },
      {
        "taskId": "task_old",
        "taskName": "Task quá hạn từ tháng trước",
        "status": "OVERDUE",
        "scheduledDuration": 0,
        "remainingEffort": 120,
        "explanation": "Deadline has expired (2026-07-30T17:00:00Z). Cannot schedule into future slots due to hard deadline constraint.",
        "energyMatch": "Standard",
        "urgencyFactor": "Urgency: 350.0",
        "conflictResolution": "Immediate action needed: extend deadline or adjust task priority/effort."
      }
    ],
    "insightsAndTips": [
      "🚨 You have 1 overdue task(s). Review deadlines or resolve them to prevent backlog pileup."
    ]
  },
  "stabilityStatus": "Committed new schedule (Reason: INITIAL_SCHEDULE_CREATED, Improvement: 1.0%)",
  "pipelineTrace": {
    "horizonStart": "2026-08-29T00:00:00+07:00",
    "horizonEnd": "2026-08-31T00:00:00+07:00",
    "freeSlotsCount": 4,
    "totalFreeMinutes": 420,
    "strategyBuckets": {
      "critical": ["Viết báo cáo kỹ thuật"],
      "competition": [],
      "normal": []
    },
    "candidatesEvaluatedCount": 2,
    "repairsApplied": 0,
    "localSearchSwaps": 0,
    "stabilityImprovementRate": 1.0,
    "stabilityAction": "COMMITTED",
    "initialScore": 105.0,
    "finalScore": 105.0,
    "elapsedSeconds": 0.018
  },
  "message": "Optimization pipeline finished successfully."
}
```

---

## 5. Phân biệt các Trạng thái trong `updatedTasks`

Thuật toán quản lý trạng thái động của công việc một cách nghiêm ngặt:

| Trạng thái | Điều kiện kích hoạt | Hành động của thuật toán | Hành động khuyến nghị cho bạn |
| :--- | :--- | :--- | :--- |
| **`COMPLETED`** | Đã được xếp đủ 100% thời gian (`remaining_effort == 0`). | Công việc hoàn tất việc lập lịch trong chu kỳ này. | Cập nhật Todo list thành trạng thái sẵn sàng thực hiện. |
| **`PARTIAL`** | Được xếp một phần thời gian (`scheduled > 0` và `remaining > 0`), hạn chót chưa qua. | Cơ chế *Stateful Spanning* ghi nhận số phút đã xếp hôm nay và tự động mang số phút còn lại sang ngày hôm sau. | Hiển thị tiến độ đang làm dở dang. |
| **`DEFERRED`** | Không xếp được phút nào (`scheduled == 0`) vì thiếu khe rảnh, **nhưng hạn chót chưa qua**. | Tăng `deferral_count += 1`. Ở lần chạy sau, cơ chế *Starvation Aging* sẽ tự động tăng vọt điểm ưu tiên để ép xếp vào lịch. | Cứ để yên, hệ thống sẽ tự xếp vào ngày hôm sau. |
| **`OVERDUE`** | **Hạn chót đã nằm trong quá khứ so với thời điểm chạy (`deadline < current_time`)** mà công việc vẫn chưa xong (`remaining > 0`). | Ràng buộc cứng cấm xếp việc quá hạn vào tương lai. Thuật toán **không xếp** và báo cáo minh bạch trong `xaiReport`. | **Cần can thiệp:** Lùi hạn chót (gia hạn deadline) hoặc xóa/hủy task. |

---

## 6. Kiểm tra Trạng thái & Debug (Health Check & Logs)

- **Health Check Endpoint:** `GET http://localhost:5000/health` (trả về `{"status": "ok"}`).
- **Xem Logs:** Vào Home Assistant -> **Settings** -> **Add-ons** -> **Smart Calendar Scheduler** -> Tab **Log** để xem nhật ký tính toán.
