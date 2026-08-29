import unittest
from datetime import datetime, timedelta

from src.models.schemas import (
    Task, FixedEvent, UserPreferences, ScheduleRequest, ScheduledSession,
    CandidateSchedule, UserFeedbackEvent
)
from src.core.constraints import (
    build_planning_horizon, compute_free_slots, validate_hard_constraints
)
from src.core.urgency import (
    calculate_dynamic_urgency, apply_starvation_aging, classify_strategy_buckets
)
from src.core.generation import (
    generate_candidate_sessions, generate_strategy_candidates, build_schedule_from_sequence
)
from src.core.evaluator import evaluate_schedule
from src.core.repair import run_schedule_repair_engine
from src.core.local_search import (
    partition_time_fences, check_schedule_stability, run_limited_local_search
)
from src.core.spanning import (
    apply_stateful_spanning, update_estimation_bias, generate_xai_report
)
from src.core.engine import run_smart_scheduler_pipeline


# ============================================================================
# TẦNG 1 (TIER A): HORIZON & HARD CONSTRAINTS (Khung thời gian & Ràng buộc cứng)
# ============================================================================
class TestTier1_HardConstraints(unittest.TestCase):

    def setUp(self):
        self.base_time = datetime(2026, 8, 29, 8, 0, 0)
        self.pref = UserPreferences(
            working_hours=[480, 1020], # 8:00 to 17:00 (540 mins)
            buffer_time=15
        )

    def test_tier_1_horizon_and_free_slots_with_buffer(self):
        """Kiểm tra tạo khe rảnh tự động né sự kiện cố định và cộng thêm buffer 15p"""
        meeting = FixedEvent(
            id="meet1", name="Daily Standup",
            startTime="2026-08-29T10:00:00", endTime="2026-08-29T11:00:00", is_busy=True
        )
        horizon = build_planning_horizon(self.base_time, [], max_days=1)
        slots = compute_free_slots(horizon, [meeting], self.pref, self.base_time)

        # Có 2 khe rảnh: 8:00 -> 9:45 (105p) và 11:15 -> 17:00 (345p)
        self.assertEqual(len(slots), 2)
        self.assertEqual(slots[0].duration, 105)
        self.assertEqual(slots[1].duration, 345)

    def test_tier_1_inter_session_overlap_prevention(self):
        """Kiểm tra bắt lỗi vi phạm khi 2 phiên làm việc bị xếp đè giờ nhau"""
        s1 = ScheduledSession(
            sessionId="s1", taskId="t1", taskName="T1",
            startTime="2026-08-29T08:00:00", endTime="2026-08-29T09:00:00",
            duration=60, contextType="general"
        )
        s2_overlap = ScheduledSession(
            sessionId="s2", taskId="t2", taskName="T2",
            startTime="2026-08-29T08:30:00", endTime="2026-08-29T09:30:00",
            duration=60, contextType="general"
        )
        tasks = [Task(id="t1", name="T1", estimated_effort=60), Task(id="t2", name="T2", estimated_effort=60)]
        val = validate_hard_constraints([s1, s2_overlap], tasks, [])
        self.assertFalse(val.is_valid)
        self.assertTrue(any("overlaps with" in v for v in val.violations))

    def test_tier_1_dependency_strict_completion_check(self):
        """Kiểm tra ràng buộc Dependency: Task con chỉ được xếp khi Task cha hoàn thành 100%"""
        task_parent = Task(id="tp", name="Task Cha", estimated_effort=60, remaining_effort=30, status="PARTIAL")
        task_child = Task(id="tc", name="Task Con", estimated_effort=60, dependencies=["tp"])
        
        s_child = ScheduledSession(
            sessionId="sc", taskId="tc", taskName="Task Con",
            startTime="2026-08-29T11:15:00", endTime="2026-08-29T12:15:00",
            duration=60, contextType="general"
        )
        val = validate_hard_constraints([s_child], [task_parent, task_child], [])
        self.assertFalse(val.is_valid)
        self.assertTrue(any("Dependency Unfulfilled" in v for v in val.violations))


# ============================================================================
# TẦNG 2 (TIER B): DYNAMIC URGENCY & STARVATION AGING (Độ khẩn cấp & Chống bỏ đói)
# ============================================================================
class TestTier2_UrgencyAndStarvation(unittest.TestCase):

    def setUp(self):
        self.base_time = datetime(2026, 8, 29, 8, 0, 0)

    def test_tier_2_dynamic_urgency_by_slack_time(self):
        """Kiểm tra độ khẩn cấp tự động tăng vọt khi thời gian chùng (Slack) co hẹp"""
        # Deadline 10:00 (Slack = 120p - 60p = 60p)
        t_urgent = Task(id="u1", name="Urgent", estimated_effort=60, deadline="2026-08-29T10:00:00", priority=3)
        # Deadline ngày mai (Slack = 1500p)
        t_relax = Task(id="r1", name="Relax", estimated_effort=60, deadline="2026-08-30T10:00:00", priority=3)

        u1 = calculate_dynamic_urgency(t_urgent, self.base_time)
        u2 = calculate_dynamic_urgency(t_relax, self.base_time)

        self.assertEqual(u1.slack_minutes, 60)
        self.assertGreater(u1.effectiveUrgency, u2.effectiveUrgency)

    def test_tier_2_starvation_aging_activation(self):
        """Kiểm tra kích hoạt Starvation Aging khi deferral_count >= 3"""
        t = Task(id="t_starved", name="Starved Task", estimated_effort=60, deferral_count=3, priority=4)
        t_eval = calculate_dynamic_urgency(t, self.base_time)
        aged = apply_starvation_aging([t_eval], max_deferral_threshold=3)[0]

        self.assertTrue(aged.isStarved)
        self.assertIsNotNone(aged.starvationWarning)
        self.assertGreater(aged.effectiveUrgency, 100.0)

    def test_tier_2_strategy_bucket_classification(self):
        """Kiểm tra phân loại giỏ chiến lược (Critical, Competition, Normal)"""
        t_crit = Task(id="c", name="Critical", estimated_effort=60, remaining_effort=60, effectiveUrgency=120.0)
        t_comp1 = Task(id="cp1", name="Comp 1", estimated_effort=60, remaining_effort=60, effectiveUrgency=65.0)
        t_comp2 = Task(id="cp2", name="Comp 2", estimated_effort=60, remaining_effort=60, effectiveUrgency=60.0)
        t_norm = Task(id="n", name="Normal", estimated_effort=60, remaining_effort=60, effectiveUrgency=30.0)

        buckets = classify_strategy_buckets([t_crit, t_comp1, t_comp2, t_norm])
        self.assertEqual(len(buckets.critical), 1)
        self.assertEqual(len(buckets.competition), 2)
        self.assertEqual(len(buckets.normal), 1)


# ============================================================================
# TẦNG 3 (TIER C): CANDIDATE GENERATION (Sinh tổ hợp phiên & Chiến lược)
# ============================================================================
class TestTier3_CandidateGeneration(unittest.TestCase):

    def test_tier_3_large_task_duration_chunking(self):
        """Kiểm tra thuật toán tự động chia nhỏ Task 210 phút thành các phiên tiêu chuẩn"""
        combos = generate_candidate_sessions(210)
        self.assertTrue(len(combos) > 0)
        self.assertEqual(sum(combos[0]), 210)
        self.assertTrue(all(c in [120, 90, 60, 45, 30] for c in combos[0]))

    def test_tier_3_batch_and_interleave_scenario_generation(self):
        """Kiểm tra sinh các kịch bản cạnh tranh BATCH và INTERLEAVE"""
        t1 = Task(id="c1", name="Coding 1", estimated_effort=60, contextType="coding")
        t2 = Task(id="c2", name="Coding 2", estimated_effort=60, contextType="coding")
        t3 = Task(id="w1", name="Writing 1", estimated_effort=60, contextType="writing")

        candidates = generate_strategy_candidates([t1, t2, t3])
        strat_types = [c["type"] for c in candidates]
        self.assertIn("BATCH", strat_types)
        self.assertIn("INTERLEAVE", strat_types)


# ============================================================================
# TẦNG 4 (TIER D): EVALUATOR, REPAIR & STABILITY (Chấm điểm J, Gỡ rối, Chống nhiễu)
# ============================================================================
class TestTier4_EvaluatorRepairStability(unittest.TestCase):

    def setUp(self):
        self.base_time = datetime(2026, 8, 29, 8, 0, 0)
        self.pref = UserPreferences(
            weights={"wCompleted": 1.0, "wTardiness": 2.5, "wSwitching": 15.0, "wFragmentation": 20.0, "wPreference": 10.0}
        )

    def test_tier_4_global_score_penalties(self):
        """Kiểm tra tính điểm phạt chuyển đổi ngữ cảnh (Switching Cost) và phân mảnh (Fragmentation)"""
        t1 = Task(id="t1", name="Coding", estimated_effort=60, contextType="coding")
        t2 = Task(id="t2", name="Writing", estimated_effort=60, contextType="writing")

        s1 = ScheduledSession(sessionId="s1", taskId="t1", taskName="Coding", startTime="2026-08-29T08:00:00", endTime="2026-08-29T09:00:00", duration=60, contextType="coding")
        # Cách nhau 15p (< 30p) và khác ngữ cảnh -> phạt switching cost 15.0
        s2 = ScheduledSession(sessionId="s2", taskId="t2", taskName="Writing", startTime="2026-08-29T09:15:00", endTime="2026-08-29T10:15:00", duration=60, contextType="writing")

        sched = CandidateSchedule(
            id="t4", sessions=[s1, s2],
            remainingSlots=[{"startTime": "2026-08-29T10:15:00", "endTime": "2026-08-29T10:25:00", "duration": 10}] # Khe < 30p -> phạt fragmentation 20.0
        )
        eval_res = evaluate_schedule(sched, [t1, t2], self.pref)

        self.assertEqual(eval_res.scoreBreakdown.switchingCostPenalty, 15.0)
        self.assertEqual(eval_res.scoreBreakdown.fragmentationPenalty, 20.0)

    def test_tier_4_repair_engine_try_shrink(self):
        """Kiểm tra Repair Engine co ngắn task ít khẩn cấp (90p -> 60p) để cứu task khẩn cấp (30p)"""
        t_low = Task(id="t_low", name="Task Thấp", estimated_effort=90, priority=4, effectiveUrgency=30.0)
        t_urgent = Task(id="t_urg", name="Task Khẩn", estimated_effort=30, priority=1, isStarved=True, effectiveUrgency=200.0)

        s_low = ScheduledSession(sessionId="slow", taskId="t_low", taskName="Task Thấp", startTime="2026-08-29T08:00:00", endTime="2026-08-29T09:30:00", duration=90)
        sched = CandidateSchedule(id="base", sessions=[s_low])

        repaired = run_schedule_repair_engine(sched, [t_low, t_urgent], [], self.pref)
        self.assertEqual(len(repaired.sessions), 2)
        task_ids = [s.taskId for s in repaired.sessions]
        self.assertIn("t_urg", task_ids)

    def test_tier_4_schedule_nervousness_stability_guard(self):
        """Kiểm tra cơ chế chống đổi lịch liên tục nếu điểm cải thiện < 10%"""
        s1 = ScheduledSession(sessionId="s1", taskId="t1", taskName="T1", startTime="2026-08-29T08:00:00", endTime="2026-08-29T09:00:00", duration=60)
        old_schedule = [s1]
        new_candidate = CandidateSchedule(id="c_new", sessions=[s1])

        t1 = Task(id="t1", name="T1", estimated_effort=60)
        stability = check_schedule_stability(new_candidate, old_schedule, [t1], [], self.base_time, self.pref)

        # Không có cải thiện vượt bậc -> Giữ lịch cũ
        self.assertFalse(stability.should_update)
        self.assertEqual(stability.reason, "REJECTED_NERVOUSNESS_GUARD")


# ============================================================================
# TẦNG 5 (TIER E): SPANNING, ADAPTIVE LEARNING & XAI (Trạng thái, Tự học, Báo cáo)
# ============================================================================
class TestTier5_SpanningLearningAndXAI(unittest.TestCase):

    def setUp(self):
        self.base_time = datetime(2026, 8, 29, 8, 0, 0)
        self.pref = UserPreferences()

    def test_tier_5_stateful_spanning_state_transitions(self):
        """Kiểm tra chuyển đổi trạng thái Stateful Spanning: UNSCHEDULED -> PARTIAL -> COMPLETED"""
        task = Task(id="t_big", name="Dự án 180p", estimated_effort=180, remaining_effort=180, status="UNSCHEDULED")
        
        # Xếp 90p hôm nay
        s1 = ScheduledSession(sessionId="s1", taskId="t_big", taskName="Dự án 180p", startTime="2026-08-29T08:00:00", endTime="2026-08-29T09:30:00", duration=90)
        sched = CandidateSchedule(id="s_span", sessions=[s1])

        updated = apply_stateful_spanning(sched, [task])
        self.assertEqual(updated[0].status, "PARTIAL")
        self.assertEqual(updated[0].completed_effort, 90)
        self.assertEqual(updated[0].remaining_effort, 90)
        self.assertTrue(updated[0].isSpanning)

    def test_tier_5_adaptive_estimation_bias_learning_ema(self):
        """Kiểm tra tự học sai số ước lượng thời gian qua Exponential Moving Average (EMA)"""
        pref = UserPreferences(estimationBiasFactor=1.0)
        # Người dùng ước lượng 60p nhưng làm thực tế mất 90p (tỷ lệ = 1.5)
        feedbacks = [UserFeedbackEvent(eventType="TASK_COMPLETED", taskId="t1", scheduledDuration=60, actualDuration=90)]
        new_pref = update_estimation_bias(pref, feedbacks)

        # alpha mới = 0.85 * 1.0 + 0.15 * 1.5 = 1.075
        self.assertGreater(new_pref.estimationBiasFactor, 1.0)
        self.assertAlmostEqual(new_pref.estimationBiasFactor, 1.075, places=2)

    def test_tier_5_xai_explainability_report(self):
        """Kiểm tra tạo báo cáo giải trình minh bạch Explainable AI (XAI Report)"""
        task = Task(id="t1", name="Coding", estimated_effort=60, status="COMPLETED", remaining_effort=0)
        s1 = ScheduledSession(sessionId="s1", taskId="t1", taskName="Coding", startTime="2026-08-29T08:00:00", endTime="2026-08-29T09:00:00", duration=60, contextType="coding")
        sched = CandidateSchedule(id="xai_test", sessions=[s1])

        report = generate_xai_report(sched, [task], self.pref)
        self.assertEqual(report.summary.totalTasks, 1)
        self.assertEqual(report.summary.completedCount, 1)
        self.assertTrue(len(report.taskExplanations) > 0)
        self.assertIn("Coding", report.taskExplanations[0].taskName)


# ============================================================================
# END-TO-END PIPELINE & SCHEMA VALIDATION (Kiểm thử toàn diện)
# ============================================================================
class TestFullPipeline(unittest.TestCase):

    def test_end_to_end_pipeline_execution(self):
        """Kiểm tra chạy toàn bộ Pipeline từ đầu đến cuối"""
        now = datetime(2026, 8, 29, 8, 0, 0)
        task1 = Task(id="t1", name="Urgent Bug", estimated_effort=60, priority=1, contextType="coding")
        task2 = Task(id="t2", name="Documentation", estimated_effort=45, priority=3, contextType="writing")
        
        req = ScheduleRequest(
            tasks=[task1, task2],
            fixedEvents=[],
            userPreferences=UserPreferences(working_hours=[480, 1020], buffer_time=15),
            current_time=now.isoformat()
        )
        res = run_smart_scheduler_pipeline(req)

        self.assertTrue(res.success)
        self.assertEqual(len(res.sessions), 2)
        self.assertIsNotNone(res.xaiReport)
        self.assertIsNotNone(res.scoreBreakdown)

    def test_pydantic_schema_validation_rules(self):
        """Kiểm tra bắt lỗi schema đầu vào"""
        # Effort <= 0
        with self.assertRaises(Exception):
            Task(id="bad", name="Bad", estimated_effort=0)
        # Working hours start >= end
        with self.assertRaises(Exception):
            UserPreferences(working_hours=[600, 500])


if __name__ == "__main__":
    unittest.main()
