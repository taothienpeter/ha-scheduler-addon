import math
import random
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional, Any
from src.models.schemas import Task, ScheduledSession, CandidateSchedule, FixedEvent, UserPreferences
from .constraints import parse_iso_datetime, validate_hard_constraints
from .evaluator import evaluate_schedule

def generate_neighbor_state(schedule: CandidateSchedule) -> CandidateSchedule:
    cloned_sessions = [s.model_copy() for s in schedule.sessions]
    if len(cloned_sessions) < 2:
        return schedule

    rand_op = random.random()

    if rand_op < 0.7:
        # Operator 1: Swap task assignments between 2 sessions with similar duration (<= 30m diff)
        idx1 = random.randint(0, len(cloned_sessions) - 1)
        idx2 = random.randint(0, len(cloned_sessions) - 1)
        while idx2 == idx1:
            idx2 = random.randint(0, len(cloned_sessions) - 1)

        s1 = cloned_sessions[idx1]
        s2 = cloned_sessions[idx2]

        if abs(s1.duration - s2.duration) <= 30 and not s1.isFrozen and not s2.isFrozen:
            temp_tid = s1.taskId
            temp_tname = s1.taskName
            temp_ctx = s1.contextType
            temp_pref = s1.preferredTime

            s1.taskId = s2.taskId
            s1.taskName = s2.taskName
            s1.contextType = s2.contextType
            s1.preferredTime = s2.preferredTime

            s2.taskId = temp_tid
            s2.taskName = temp_tname
            s2.contextType = temp_ctx
            s2.preferredTime = temp_pref
    else:
        # Operator 2: Nudge session start time by +/- 15 mins if not frozen
        idx = random.randint(0, len(cloned_sessions) - 1)
        s = cloned_sessions[idx]
        if not s.isFrozen:
            shift_m = 15 if random.random() > 0.5 else -15
            st = parse_iso_datetime(s.startTime)
            et = parse_iso_datetime(s.endTime)
            if st and et:
                s.startTime = (st + timedelta(minutes=shift_m)).isoformat()
                s.endTime = (et + timedelta(minutes=shift_m)).isoformat()

    new_cand = schedule.model_copy()
    new_cand.sessions = cloned_sessions
    return new_cand

def run_limited_local_search(
    base_schedule: CandidateSchedule,
    all_tasks: List[Task],
    fixed_events: List[FixedEvent],
    user_pref: UserPreferences,
    max_iterations: int = 50
) -> CandidateSchedule:
    current_best = evaluate_schedule(base_schedule, all_tasks, user_pref)
    current_best_score = current_best.scoreBreakdown.finalScore if current_best.scoreBreakdown else 0.0

    if not current_best.sessions or len(current_best.sessions) < 2:
        return current_best

    for _ in range(max_iterations):
        neighbor = generate_neighbor_state(current_best)

        # 1. Hard Constraints Check (Ensures swapped/nudged sessions don't violate constraints)
        validation = validate_hard_constraints(neighbor.sessions, all_tasks, fixed_events)
        if not validation.valid:
            continue

        # 2. Score Neighbor
        evaluated_neighbor = evaluate_schedule(neighbor, all_tasks, user_pref)
        neighbor_score = evaluated_neighbor.scoreBreakdown.finalScore if evaluated_neighbor.scoreBreakdown else -9999.0

        # 3. Hill Climbing Acceptance
        if neighbor_score > current_best_score:
            current_best = evaluated_neighbor
            current_best_score = neighbor_score

    return current_best

class StabilityCheckResult:
    def __init__(self, should_update: bool, reason: str, improvement_rate: float, old_score: float, new_score: float):
        self.should_update = should_update
        self.reason = reason
        self.improvement_rate = improvement_rate
        self.old_score = old_score
        self.new_score = new_score

def check_schedule_stability(
    new_schedule: CandidateSchedule,
    old_sessions: Optional[List[ScheduledSession]],
    all_tasks: List[Task],
    fixed_events: List[FixedEvent],
    current_time: datetime,
    user_pref: UserPreferences
) -> StabilityCheckResult:
    # If no previous schedule exists, commit immediately
    if not old_sessions or len(old_sessions) == 0:
        new_score = new_schedule.scoreBreakdown.finalScore if new_schedule.scoreBreakdown else 0.0
        return StabilityCheckResult(
            should_update=True,
            reason="INITIAL_SCHEDULE_CREATED",
            improvement_rate=1.0,
            old_score=0.0,
            new_score=new_score
        )

    # 1. Check if old schedule is still valid with current constraints
    old_validation = validate_hard_constraints(old_sessions, all_tasks, fixed_events)
    if not old_validation.valid:
        new_score = new_schedule.scoreBreakdown.finalScore if new_schedule.scoreBreakdown else 0.0
        return StabilityCheckResult(
            should_update=True,
            reason="OLD_SCHEDULE_INVALID",
            improvement_rate=1.0,
            old_score=0.0,
            new_score=new_score
        )

    # 2. Score both old and new schedules on same objective weights
    old_candidate = CandidateSchedule(id="old_schedule", sessions=old_sessions)
    evaluated_old = evaluate_schedule(old_candidate, all_tasks, user_pref)
    
    old_score = evaluated_old.scoreBreakdown.finalScore if evaluated_old.scoreBreakdown else 0.0
    new_score = new_schedule.scoreBreakdown.finalScore if new_schedule.scoreBreakdown else 0.0

    # BUG #7 FIX: Guard against NaN, Inf or undefined values
    if math.isnan(old_score) or math.isinf(old_score) or math.isnan(new_score) or math.isinf(new_score):
        return StabilityCheckResult(
            should_update=True,
            reason="EVALUATION_FALLBACK_VALID",
            improvement_rate=0.0,
            old_score=0.0,
            new_score=0.0
        )

    denominator = max(abs(old_score), 1.0)
    improvement_rate = (new_score - old_score) / denominator

    # 3. Check Reschedule Threshold (e.g. >= 10%)
    threshold = user_pref.rescheduleThreshold or 0.10
    if improvement_rate >= threshold:
        return StabilityCheckResult(
            should_update=True,
            reason="SIGNIFICANT_IMPROVEMENT",
            improvement_rate=round(improvement_rate * 100, 2),
            old_score=old_score,
            new_score=new_score
        )

    # 4. Otherwise reject to prevent schedule nervousness
    return StabilityCheckResult(
        should_update=False,
        reason="REJECTED_NERVOUSNESS_GUARD",
        improvement_rate=round(improvement_rate * 100, 2),
        old_score=old_score,
        new_score=new_score
    )

def partition_time_fences(
    sessions: List[ScheduledSession],
    current_time: datetime,
    frozen_zone_hours: int = 3
) -> List[ScheduledSession]:
    frozen_threshold = current_time + timedelta(hours=frozen_zone_hours)
    result = []
    for s in sessions:
        st = parse_iso_datetime(s.startTime)
        s_copy = s.model_copy()
        if st and st < frozen_threshold:
            s_copy.isFrozen = True
        result.append(s_copy)
    return result
