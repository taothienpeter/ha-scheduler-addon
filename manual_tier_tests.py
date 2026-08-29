"""
HUONG DAN KIEM TRA THU CONG 5 TANG THUAT TOAN SMART SCHEDULING
Chay lenh: .\\venv\\Scripts\\python.exe manual_tier_tests.py
"""
import sys
from datetime import datetime, timedelta

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.models.schemas import (
    Task, FixedEvent, UserPreferences, ScheduledSession, 
    CandidateSchedule, UserFeedbackEvent
)
from src.core.constraints import compute_free_slots, validate_hard_constraints, build_planning_horizon
from src.core.urgency import calculate_dynamic_urgency, apply_starvation_aging, classify_strategy_buckets
from src.core.generation import generate_candidate_sessions, generate_strategy_candidates
from src.core.evaluator import evaluate_schedule
from src.core.repair import run_schedule_repair_engine
from src.core.local_search import check_schedule_stability, partition_time_fences
from src.core.spanning import apply_stateful_spanning, update_estimation_bias, generate_xai_report

def test_tier_a():
    print("\n" + "=" * 75)
    print("🔹 TẦNG A: HORIZON & HARD CONSTRAINTS (Kiểm tra Lọc Khung Giờ & Ràng Buộc Cứng)")
    print("=" * 75)
    
    now = datetime(2026, 8, 29, 8, 0) # 8:00 AM
    pref = UserPreferences(working_hours=[480, 1020], buffer_time=15) # 8:00 - 17:00, đệm 15p
    
    # 1. Test tính khe trống (Free Slots)
    fixed_event = FixedEvent(
        id="m1", name="Họp Team",
        startTime="2026-08-29T10:00:00", endTime="2026-08-29T11:00:00", is_busy=True
    )
    horizon = build_planning_horizon(now, [], max_days=1)
    slots = compute_free_slots(horizon, [fixed_event], pref, now)
    
    print("1. Kiểm tra tính Khe Thời Gian Rảnh (Free Slots) né lịch họp 10:00-11:00:")
    for s in slots:
        st = s.startTime.strftime('%H:%M')
        et = s.endTime.strftime('%H:%M')
        print(f"   👉 Khe rảnh: [{st} - {et}] (Dung lượng: {s.duration} phút)")
    
    # 2. Test kiểm tra Overlap giữa 2 session
    s1 = ScheduledSession(sessionId="s1", taskId="t1", taskName="Task 1", startTime="2026-08-29T08:00:00", endTime="2026-08-29T09:00:00", duration=60)
    s2_overlap = ScheduledSession(sessionId="s2", taskId="t2", taskName="Task 2 (Đè giờ)", startTime="2026-08-29T08:30:00", endTime="2026-08-29T09:30:00", duration=60)
    candidate_bad = CandidateSchedule(id="bad", sessions=[s1, s2_overlap])
    
    val_overlap = validate_hard_constraints(candidate_bad.sessions, [], [])
    print(f"\n2. Kiểm tra phát hiện lỗi Đè Giờ (Overlap):")
    print(f"   👉 Hợp lệ? {val_overlap.is_valid} | Lý do vi phạm: '{val_overlap.violations[0] if val_overlap.violations else 'None'}'")

    # 3. Test ràng buộc Dependency
    t_parent = Task(id="tp", name="Task Cha", estimated_effort=60, remaining_effort=30, status="PARTIAL") # Chưa xong 100%
    t_child = Task(id="tc", name="Task Con", estimated_effort=60, dependencies=["tp"])
    session_child = ScheduledSession(sessionId="sc", taskId="tc", taskName="Task Con", startTime="2026-08-29T11:15:00", endTime="2026-08-29T12:15:00", duration=60)
    
    val_dep = validate_hard_constraints([session_child], [t_parent, t_child], [])
    print(f"\n3. Kiểm tra ràng buộc Dependency (Task con chạy khi Task cha mới xong 50%):")
    print(f"   👉 Hợp lệ? {val_dep.is_valid} | Lý do vi phạm: '{val_dep.violations[0] if val_dep.violations else 'None'}'")

def test_tier_b():
    print("\n" + "=" * 75)
    print("🔹 TẦNG B: DYNAMIC URGENCY & STARVATION AGING (Tính Độ Khẩn Cấp & Chống Bỏ Đói)")
    print("=" * 75)
    
    now = datetime(2026, 8, 29, 8, 0)
    
    # 1. So sánh Slack time
    t_urgent = Task(id="t1", name="Task gấp (Deadline 10h)", estimated_effort=60, priority=3, deadline="2026-08-29T10:00:00")
    t_relax = Task(id="t2", name="Task thảnh thơi (Deadline ngày mai)", estimated_effort=60, priority=3, deadline="2026-08-30T10:00:00")
    
    u1 = calculate_dynamic_urgency(t_urgent, now)
    u2 = calculate_dynamic_urgency(t_relax, now)
    
    print("1. Độ khẩn cấp động (Dynamic Urgency) theo Slack Time:")
    print(f"   👉 {t_urgent.name}: Slack = {u1.slack_minutes}p -> Urgency Score = {u1.effectiveUrgency:.1f}")
    print(f"   👉 {t_relax.name}: Slack = {u2.slack_minutes}p -> Urgency Score = {u2.effectiveUrgency:.1f}")
    
    # 2. Starvation Aging (Bị hoãn 3 lần)
    t_starved = Task(id="t3", name="Task bị bỏ rơi", estimated_effort=60, priority=4, deferral_count=3)
    t_starved = calculate_dynamic_urgency(t_starved, now)
    tasks_aged = apply_starvation_aging([t_starved], max_deferral_threshold=3)
    
    print("\n2. Cơ chế Starvation Aging kích hoạt khi `deferral_count >= 3`:")
    print(f"   👉 Bị bỏ đói (isStarved)? {tasks_aged[0].isStarved}")
    print(f"   👉 Cảnh báo: {tasks_aged[0].starvationWarning}")
    print(f"   👉 Urgency ban đầu = {t_starved.effectiveUrgency:.1f} -> Sau kích hoạt = {tasks_aged[0].effectiveUrgency:.1f}")

def test_tier_c():
    print("\n" + "=" * 75)
    print("🔹 TẦNG C: CANDIDATE GENERATION (Sinh Tổ Hợp Phiên & Chiến Lược Lập Lịch)")
    print("=" * 75)
    
    # 1. Chia nhỏ task 210 phút
    task_210 = Task(id="t_big", name="Task Lớn 210 phút", estimated_effort=210)
    combos = generate_candidate_sessions(task_210.estimated_effort)
    
    print("1. Thuật toán tự động chia nhỏ Task 210 phút thành các phiên làm việc tiêu chuẩn:")
    for idx, c in enumerate(combos, 1):
        print(f"   👉 Phương án {idx}: {c} phút (Tổng = {sum(c)}p)")
        
    # 2. Sinh các kịch bản cạnh tranh (Batching vs Interleaving)
    t_code1 = Task(id="c1", name="Code API", estimated_effort=60, contextType="coding", priority=2)
    t_code2 = Task(id="c2", name="Code Database", estimated_effort=60, contextType="coding", priority=2)
    t_write = Task(id="w1", name="Viết Docs", estimated_effort=60, contextType="writing", priority=2)
    
    strats = generate_strategy_candidates([t_code1, t_code2, t_write])
    print("\n2. Sinh các kịch bản chiến lược (Scenarios):")
    for s in strats:
        print(f"   👉 Chiến lược [{s['type']}]: Thứ tự task = {s['sequence']}")

def test_tier_d():
    print("\n" + "=" * 75)
    print("🔹 TẦNG D: GLOBAL EVALUATOR, REPAIR & STABILITY (Chấm Điểm J, Gỡ Rối & Chống Nhiễu Lịch)")
    print("=" * 75)
    
    now = datetime(2026, 8, 29, 8, 0)
    pref = UserPreferences()
    
    # 1. Chấm điểm hàm J
    t1 = Task(id="t1", name="Coding", estimated_effort=60, contextType="coding")
    t2 = Task(id="t2", name="Writing", estimated_effort=60, contextType="writing")
    
    s1 = ScheduledSession(sessionId="s1", taskId="t1", taskName="Coding", startTime="2026-08-29T08:00:00", endTime="2026-08-29T09:00:00", duration=60, contextType="coding")
    # Đổi ngữ cảnh Coding -> Writing sát nhau (< 30p)
    s2 = ScheduledSession(sessionId="s2", taskId="t2", taskName="Writing", startTime="2026-08-29T09:15:00", endTime="2026-08-29T10:15:00", duration=60, contextType="writing")
    
    sched = CandidateSchedule(id="s_eval", sessions=[s1, s2])
    eval_res = evaluate_schedule(sched, [t1, t2], pref)
    
    print("1. Chấm điểm toàn cục (Global Score J):")
    print(f"   👉 Điểm tổng thể J = {eval_res.scoreBreakdown.finalScore:.1f}")
    print(f"   👉 Phạt đổi ngữ cảnh liên tục (Switching Cost): -{eval_res.scoreBreakdown.switchingCostPenalty:.1f}")
    
    # 2. Repair Engine: Co ngắn task (try_shrink)
    t_less = Task(id="t_low", name="Task thấp điểm (90p)", estimated_effort=90, priority=4)
    t_starv = Task(id="t_starv", name="Task khẩn cấp (30p)", estimated_effort=30, priority=1, isStarved=True, effectiveUrgency=200.0)
    
    s_low = ScheduledSession(sessionId="slow", taskId="t_low", taskName="Task thấp điểm", startTime="2026-08-29T08:00:00", endTime="2026-08-29T09:30:00", duration=90)
    repaired = run_schedule_repair_engine(CandidateSchedule(id="base", sessions=[s_low]), [t_less, t_starv], [], pref)
    
    print("\n2. Thuật toán tự gỡ rối (Repair Engine - tryShrink):")
    print(f"   👉 Trước repair: {len([s_low])} session (Task 90p chiếm hết chỗ)")
    print(f"   👉 Sau repair: {len(repaired.sessions)} session:")
    for s in repaired.sessions:
        print(f"      - {s.taskName} ({s.duration}p): [{s.startTime} -> {s.endTime}]")

    # 3. Schedule Stability (Chống đổi lịch liên tục)
    old_sched = [s1] # Lịch cũ điểm ~60
    new_sched_slight = CandidateSchedule(id="slight", sessions=[s1]) # Điểm tương đương
    stability = check_schedule_stability(new_sched_slight, old_sched, [t1], [], now, pref)
    print(f"\n3. Chống nhiễu loạn lịch (Schedule Stability Guard):")
    print(f"   👉 Có nên cập nhật lịch mới? {stability.should_update} | Lý do: '{stability.reason}'")

def test_tier_e():
    print("\n" + "=" * 75)
    print("🔹 TẦNG E: STATEFUL SPANNING, ADAPTIVE LEARNING & XAI (Trạng Thái, Học Máy & Báo Cáo)")
    print("=" * 75)
    
    # 1. Stateful Spanning
    t_span = Task(id="t_span", name="Task Dự Án Lớn", estimated_effort=180, remaining_effort=180, status="UNSCHEDULED")
    sess_today = ScheduledSession(sessionId="s1", taskId="t_span", taskName="Task Dự Án Lớn", startTime="2026-08-29T08:00:00", endTime="2026-08-29T09:30:00", duration=90)
    
    updated_tasks = apply_stateful_spanning(CandidateSchedule(id="sp", sessions=[sess_today]), [t_span])
    print("1. Chuyển đổi trạng thái Stateful Spanning (Task 180p xếp được 90p hôm nay):")
    print(f"   👉 Trạng thái mới: {updated_tasks[0].status}")
    print(f"   👉 Đã hoàn thành: {updated_tasks[0].completed_effort}p | Còn lại: {updated_tasks[0].remaining_effort}p | Spanning? {updated_tasks[0].isSpanning}")
    
    # 2. Adaptive Learning (EMA Estimation Bias)
    pref = UserPreferences(estimationBiasFactor=1.0)
    feedback = [
        UserFeedbackEvent(eventType="TASK_COMPLETED", taskId="t1", scheduledDuration=60, actualDuration=90) # Thực tế làm 90p (dài hơn 1.5 lần dự kiến)
    ]
    new_pref = update_estimation_bias(pref, feedback)
    print(f"\n2. Tự học sai số ước lượng (Adaptive Estimation Bias EMA):")
    print(f"   👉 Hệ số ban đầu = {pref.estimationBiasFactor:.2f} -> Sau khi ghi nhận làm quá giờ = {new_pref.estimationBiasFactor:.2f}")
    
    # 3. Báo cáo giải trình AI (XAI Report)
    report = generate_xai_report(CandidateSchedule(id="sp", sessions=[sess_today]), updated_tasks, pref)
    print(f"\n3. Báo cáo giải trình Explainable AI (XAI Report):")
    for expl in report.taskExplanations:
        print(f"   👉 {expl.taskName}: {expl.explanation}")

if __name__ == "__main__":
    test_tier_a()
    test_tier_b()
    test_tier_c()
    test_tier_d()
    test_tier_e()
    print("\n" + "=" * 75)
    print("🎉 HOÀN TẤT KIỂM TRA THỦ CÔNG 5 TẦNG THUẬT TOÁN!")
    print("=" * 75)
