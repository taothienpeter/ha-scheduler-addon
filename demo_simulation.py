"""
Script demo và kiểm tra trực quan thuật toán Smart Scheduling
Chay lenh: .\\venv\\Scripts\\python.exe demo_simulation.py
"""
import sys
import os

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from datetime import datetime, timedelta
from src.core.engine import run_smart_scheduler_pipeline
from src.models.schemas import ScheduleRequest, Task, FixedEvent, UserPreferences

def run_demo():
    print("=" * 70)
    print("CHAY THU NGHIEM THUAT TOAN SMART SCHEDULING (MO PHONG THUC TE)")
    print("=" * 70)

    # 1. Khoi tao thoi gian gia lap (Hom nay luc 8:00 sang)
    base_time = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
    print(f"Thoi diem bat dau xep lich: {base_time.strftime('%Y-%m-%d %H:%M')}\n")

    # 2. Danh sach Task voi cac tinh huong da dang
    tasks = [
        Task(
            id="task_urgent_bug",
            name="Fix loi Server sap (Urgent Bug)",
            estimated_effort=60, # 1 tieng
            priority=1, # Uu tien cao nhat (Critical)
            contextType="coding",
            deadline=(base_time + timedelta(hours=4)).isoformat() # Deadline 12:00 trua
        ),
        Task(
            id="task_deep_work",
            name="Phat trien tinh nang moi (Deep Work)",
            estimated_effort=180, # 3 tieng -> Se duoc tu dong chia nho thanh cac phien
            priority=2,
            contextType="coding",
            preferredTime="morning"
        ),
        Task(
            id="task_report",
            name="Viet bao cao tien do tuan (Weekly Report)",
            estimated_effort=45,
            priority=3,
            contextType="writing",
            preferredTime="afternoon"
        ),
        Task(
            id="task_admin",
            name="Tra loi email & don dep (Admin tasks)",
            estimated_effort=30,
            priority=4,
            contextType="admin"
        )
    ]

    # 3. Lich ban co dinh (Hop cong ty khong the doi)
    fixed_events = [
        FixedEvent(
            id="meeting_daily",
            name="Hop Daily Scrum",
            startTime=(base_time + timedelta(hours=1)).isoformat(), # 9:00 - 9:30
            endTime=(base_time + timedelta(hours=1, minutes=30)).isoformat(),
            is_busy=True
        ),
        FixedEvent(
            id="lunch_break",
            name="Nghi trua",
            startTime=(base_time + timedelta(hours=4)).isoformat(), # 12:00 - 13:30
            endTime=(base_time + timedelta(hours=5, minutes=30)).isoformat(),
            is_busy=True
        )
    ]

    # 4. Cau hinh nguoi dung (Gio lam viec: 8:00 - 18:00, nghi dem giua cac phien: 15p)
    user_pref = UserPreferences(
        working_hours=[480, 1080], # 8:00 (480p) -> 18:00 (1080p)
        buffer_time=15
    )

    # 5. Dong goi Request va goi Pipeline thuat toan
    request = ScheduleRequest(
        tasks=tasks,
        fixedEvents=fixed_events,
        userPreferences=user_pref,
        current_time=base_time.isoformat()
    )

    response = run_smart_scheduler_pipeline(request)

    # 6. Hien thi ket qua kiem tra
    print("KET QUA XEP LICH:")
    print(f"- Trang thai: {'Thanh cong' if response.success else 'That bai'}")
    print(f"- Tong diem toi uu hoa (Score J): {response.score:.1f}")
    if response.scoreBreakdown:
        sb = response.scoreBreakdown
        print(f"  + Diem hoan thanh task: +{sb.completedWorkScore:.1f}")
        print(f"  + Diem thuong so thich: +{sb.userPreferenceBonus:.1f}")
        print(f"  + Phat tre deadline:   -{sb.tardinessPenalty:.1f}")
        print(f"  + Phat doi ngu canh:   -{sb.switchingCostPenalty:.1f}")
        print(f"  + Phat vo vun lich:    -{sb.fragmentationPenalty:.1f}")
    
    print("\nTIMELINE LICH TRINH DUOC XEP:")
    print("-" * 70)
    for sess in response.sessions:
        st = datetime.fromisoformat(sess.startTime).strftime('%H:%M')
        et = datetime.fromisoformat(sess.endTime).strftime('%H:%M')
        print(f"  [{st} - {et}] ({sess.duration:>3}p) [{sess.contextType.upper():<7}] : {sess.taskName}")
    print("-" * 70)

    print("\nTRANG THAI TASK:")
    for t in response.updatedTasks:
        print(f"  - {t.name}: Trang thai = {t.status}, Con lai = {t.remaining_effort}p")

    if response.xaiReport:
        print("\nBAO CAO GIAI TRINH THONG MINH (XAI REPORT):")
        for expl in response.xaiReport.taskExplanations:
            print(f"  * {expl.taskName}: {expl.explanation}")

    print("\n" + "=" * 70)

if __name__ == "__main__":
    run_demo()
