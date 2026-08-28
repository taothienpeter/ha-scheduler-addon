import unittest
from datetime import datetime, timedelta

from src.models.schemas import (
    Task, FixedEvent, UserPreferences, ScheduleRequest, ScheduledSession
)
from src.core.constraints import (
    build_planning_horizon, compute_free_slots, validate_hard_constraints
)
from src.core.urgency import (
    calculate_dynamic_urgency, apply_starvation_aging, classify_strategy_buckets
)
from src.core.generation import generate_candidate_sessions
from src.core.evaluator import evaluate_schedule
from src.core.engine import run_smart_scheduler_pipeline

class TestSmartScheduler(unittest.TestCase):

    def setUp(self):
        self.base_time = datetime(2026, 8, 29, 8, 0, 0)
        self.pref = UserPreferences(
            timezone="Asia/Ho_Chi_Minh",
            working_hours=[540, 1020], # 9:00 to 17:00 (8 hours = 480 mins)
            buffer_time=15,
            weights={
                "wCompleted": 1.0,
                "wTardiness": 2.5,
                "wSwitching": 15.0,
                "wFragmentation": 20.0,
                "wOverload": 1.5,
                "wPreference": 10.0
            }
        )

    def test_dynamic_urgency_and_slack(self):
        # Task with tight deadline (4 hours from now, effort = 120 mins => slack = 120 mins)
        deadline = (self.base_time + timedelta(hours=4)).isoformat()
        t = Task(id="t1", name="Urgent Task", estimated_effort=120, deadline=deadline, priority=2)
        
        evaluated = calculate_dynamic_urgency(t, self.base_time)
        self.assertIsNotNone(evaluated.effectiveUrgency)
        self.assertEqual(evaluated.slack_minutes, 120)
        # Priority 2 base (40) + slack <= 120 bonus (100) = 140
        self.assertEqual(evaluated.effectiveUrgency, 140.0)

    def test_starvation_aging(self):
        t = Task(id="t2", name="Starved Task", estimated_effort=60, deferral_count=3, priority=4)
        aged = apply_starvation_aging([t], max_deferral_threshold=3)[0]
        
        self.assertTrue(aged.isStarved)
        self.assertIsNotNone(aged.starvationWarning)
        self.assertGreater(aged.effectiveUrgency, 30.0)

    def test_candidate_session_generation_bounded(self):
        # Test large task (480 mins) does not crash or take long
        combos = generate_candidate_sessions(480)
        self.assertTrue(len(combos) > 0)
        self.assertEqual(sum(combos[0]), 480)
        self.assertTrue(all(c in [120, 90, 60, 45, 30] for c in combos[0]))

    def test_hard_constraint_inter_session_overlap(self):
        # Two overlapping sessions
        s1 = ScheduledSession(
            sessionId="s1", taskId="t1", taskName="T1",
            startTime="2026-08-29T09:00:00Z", endTime="2026-08-29T10:00:00Z",
            duration=60, contextType="general"
        )
        s2 = ScheduledSession(
            sessionId="s2", taskId="t2", taskName="T2",
            startTime="2026-08-29T09:30:00Z", endTime="2026-08-29T10:30:00Z",
            duration=60, contextType="general"
        )
        tasks = [
            Task(id="t1", name="T1", estimated_effort=60),
            Task(id="t2", name="T2", estimated_effort=60)
        ]
        
        val = validate_hard_constraints([s1, s2], tasks, [])
        self.assertFalse(val.valid)
        self.assertTrue(any("overlaps with" in v for v in val.violations))

    def test_dependency_unfulfilled_constraint(self):
        # Task B depends on Task A. Task A is only scheduled for 30m of 60m effort.
        task_a = Task(id="tA", name="Task A", estimated_effort=60, remaining_effort=60)
        task_b = Task(id="tB", name="Task B", estimated_effort=60, dependencies=["tA"])
        
        sA = ScheduledSession(
            sessionId="sA", taskId="tA", taskName="Task A",
            startTime="2026-08-29T09:00:00Z", endTime="2026-08-29T09:30:00Z",
            duration=30, contextType="general"
        )
        sB = ScheduledSession(
            sessionId="sB", taskId="tB", taskName="Task B",
            startTime="2026-08-29T10:00:00Z", endTime="2026-08-29T11:00:00Z",
            duration=60, contextType="general"
        )
        
        val = validate_hard_constraints([sA, sB], [task_a, task_b], [])
        self.assertFalse(val.valid)
        self.assertTrue(any("Dependency Unfulfilled" in v for v in val.violations))

    def test_weight_aliases_and_energy_bonus(self):
        # Test math symbol weights (w_c, w_t)
        pref_alias = UserPreferences(
            weights={"w_c": 2.0, "w_t": 5.0, "w_s": 10.0, "w_f": 10.0, "w_o": 1.0, "w_p": 10.0}
        )
        task = Task(id="t_code", name="Coding Task", estimated_effort=60, contextType="coding")
        req = ScheduleRequest(
            tasks=[task],
            userPreferences=pref_alias,
            current_time=self.base_time.isoformat()
        )
        res = run_smart_scheduler_pipeline(req)
        self.assertTrue(res.success)
        self.assertIsNotNone(res.scoreBreakdown)
        self.assertGreater(res.scoreBreakdown.userPreferenceBonus, 0.0)

    def test_pydantic_input_validation(self):
        # Invalid estimated effort (negative or zero)
        with self.assertRaises(Exception):
            Task(id="bad", name="Bad Task", estimated_effort=0)

        # Invalid deadline string
        with self.assertRaises(Exception):
            Task(id="bad2", name="Bad Date", estimated_effort=30, deadline="not-a-date")

        # Invalid working hours range
        with self.assertRaises(Exception):
            UserPreferences(working_hours=[1000, 500])

    def test_empty_schedule(self):
        req = ScheduleRequest(
            tasks=[],
            userPreferences=self.pref,
            current_time=self.base_time.isoformat()
        )
        res = run_smart_scheduler_pipeline(req)
        self.assertTrue(res.success)
        self.assertEqual(len(res.schedule), 0)
        self.assertEqual(len(res.unassignedTasks), 0)

    def test_evaluator_penalties(self):
        # Create a candidate schedule with fragmentation and switching costs
        t1 = Task(id="t1", name="Coding", estimated_effort=60, contextType="coding", deadline=(self.base_time + timedelta(hours=4)).isoformat())
        t2 = Task(id="t2", name="Writing", estimated_effort=60, contextType="writing", deadline=(self.base_time + timedelta(hours=4)).isoformat())

        s1 = ScheduledSession(
            sessionId="s1", taskId="t1", taskName="Coding",
            startTime=self.base_time.isoformat(), endTime=(self.base_time + timedelta(minutes=60)).isoformat(),
            duration=60, contextType="coding"
        )
        # 15 min gap (switching cost penalty since different context and gap < 30)
        s2 = ScheduledSession(
            sessionId="s2", taskId="t2", taskName="Writing",
            startTime=(self.base_time + timedelta(minutes=75)).isoformat(), endTime=(self.base_time + timedelta(minutes=135)).isoformat(),
            duration=60, contextType="writing"
        )
        
        from src.models.schemas import CandidateSchedule
        sched = CandidateSchedule(
            id="test",
            strategyType="TEST",
            sessions=[s1, s2],
            remainingSlots=[{"startTime": (self.base_time + timedelta(minutes=135)).isoformat(), "endTime": (self.base_time + timedelta(minutes=145)).isoformat(), "duration": 10}] # < 30m slot => fragmentation
        )

        evaluated = evaluate_schedule(sched, [t1, t2], self.pref)
        
        # Switching cost (1 switch * 15.0)
        self.assertEqual(evaluated.scoreBreakdown.switchingCostPenalty, 15.0)
        # Fragmentation cost (1 slot * 20.0)
        self.assertEqual(evaluated.scoreBreakdown.fragmentationPenalty, 20.0)

    def test_repair_engine_resolution(self):
        from src.core.repair import run_schedule_repair_engine
        from src.models.schemas import CandidateSchedule

        # Initial schedule where T1 is scheduled, T2 is unassigned but has high urgency
        t1 = Task(id="t1", name="Task 1", estimated_effort=90, priority=2)
        t2 = Task(id="t2", name="Task 2 (Urgent)", estimated_effort=30, priority=5, isStarved=True, effectiveUrgency=200.0)
        
        t1 = calculate_dynamic_urgency(t1, self.base_time)
        t2 = calculate_dynamic_urgency(t2, self.base_time)

        s1 = ScheduledSession(
            sessionId="s1", taskId="t1", taskName="Task 1",
            startTime=self.base_time.isoformat(), endTime=(self.base_time + timedelta(minutes=90)).isoformat(),
            duration=90, contextType="general"
        )

        sched = CandidateSchedule(id="base", strategyType="TEST", sessions=[s1])
        
        repaired = run_schedule_repair_engine(
            base_schedule=sched,
            all_tasks=[t1, t2],
            fixed_events=[],
            user_pref=self.pref,
            max_attempts=5
        )

        # The repair engine should have shrunk T1 or swapped to fit T2
        # Since T2 is 30m, and T1 is 90m and less urgent, T1 should be shrunk by 30m
        self.assertEqual(len(repaired.sessions), 2)
        scheduled_tasks = [s.taskId for s in repaired.sessions]
        self.assertIn("t2", scheduled_tasks)

if __name__ == "__main__":
    unittest.main()
