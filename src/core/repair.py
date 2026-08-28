import time
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from src.models.schemas import Task, ScheduledSession, CandidateSchedule, FixedEvent, UserPreferences
from .constraints import parse_iso_datetime, validate_hard_constraints
from .evaluator import evaluate_schedule

def try_move(
    schedule: CandidateSchedule,
    target_task: Task,
    all_tasks: List[Task],
    fixed_events: List[FixedEvent]
) -> Optional[CandidateSchedule]:
    sessions = sorted(
        [s.model_copy() for s in schedule.sessions],
        key=lambda x: parse_iso_datetime(x.startTime) or datetime.min
    )
    if len(sessions) < 2:
        return None

    needed_duration = min(target_task.remaining_effort or target_task.estimated_effort, 60)
    if needed_duration < 30:
        return None

    for i in range(len(sessions) - 1):
        # BUG #5 FIX: Deep clone candidate sessions for each attempt to avoid in-place corruption
        candidate_sessions = [s.model_copy() for s in sessions]
        curr_s = candidate_sessions[i]
        next_s = candidate_sessions[i + 1]

        curr_end = parse_iso_datetime(curr_s.endTime)
        next_start = parse_iso_datetime(next_s.startTime)
        next_end = parse_iso_datetime(next_s.endTime)

        if not curr_end or not next_start or not next_end:
            continue

        gap_m = int((next_start - curr_end).total_seconds() // 60)

        # Check if shifting next_s by shift_needed can create space
        if gap_m < needed_duration and (gap_m + 30) >= needed_duration:
            shift_needed = needed_duration - gap_m
            new_next_start = next_start + timedelta(minutes=shift_needed)
            new_next_end = next_end + timedelta(minutes=shift_needed)

            # Ensure new_next_end doesn't collide with session i+2
            if i + 2 < len(candidate_sessions):
                subsequent_start = parse_iso_datetime(candidate_sessions[i + 2].startTime)
                if subsequent_start and new_next_end > subsequent_start:
                    continue

            # Update cloned next_s
            next_s.startTime = new_next_start.isoformat()
            next_s.endTime = new_next_end.isoformat()

            # Insert target task in the newly created gap
            insert_start = curr_end
            insert_end = insert_start + timedelta(minutes=needed_duration)
            new_sess = ScheduledSession(
                sessionId=f"repair_move_{target_task.id}_{len(candidate_sessions) + 1}",
                taskId=target_task.id,
                taskName=target_task.name,
                startTime=insert_start.isoformat(),
                endTime=insert_end.isoformat(),
                duration=needed_duration,
                contextType=target_task.contextType or "general",
                preferredTime=target_task.preferredTime
            )
            candidate_sessions.append(new_sess)

            validation = validate_hard_constraints(candidate_sessions, all_tasks, fixed_events)
            if validation.valid:
                new_cand = schedule.model_copy()
                new_cand.sessions = candidate_sessions
                return new_cand

    return None

def try_swap(
    schedule: CandidateSchedule,
    target_task: Task,
    all_tasks: List[Task],
    fixed_events: List[FixedEvent]
) -> Optional[CandidateSchedule]:
    sessions = sorted(
        [s.model_copy() for s in schedule.sessions],
        key=lambda x: parse_iso_datetime(x.startTime) or datetime.min
    )
    task_map = {t.id: t for t in all_tasks}

    needed_duration = min(target_task.remaining_effort or target_task.estimated_effort, 60)
    target_urgency = target_task.effectiveUrgency or 30.0

    for i, victim_sess in enumerate(sessions):
        victim_task = task_map.get(victim_sess.taskId)
        if not victim_task:
            continue

        victim_urgency = victim_task.effectiveUrgency or 30.0
        
        # Only swap if victim has noticeably lower urgency and enough duration
        if victim_urgency < (target_urgency - 20.0) and victim_sess.duration >= needed_duration:
            v_start = parse_iso_datetime(victim_sess.startTime)
            if not v_start:
                continue

            # BUG #5 FIX: Deep copy candidate sessions
            candidate_sessions = [s.model_copy() for s in sessions]
            cloned_victim = candidate_sessions[i]

            new_target_end = v_start + timedelta(minutes=needed_duration)
            new_target_sess = ScheduledSession(
                sessionId=f"repair_swap_{target_task.id}_{len(candidate_sessions) + 1}",
                taskId=target_task.id,
                taskName=target_task.name,
                startTime=v_start.isoformat(),
                endTime=new_target_end.isoformat(),
                duration=needed_duration,
                contextType=target_task.contextType or "general",
                preferredTime=target_task.preferredTime
            )

            leftover_duration = cloned_victim.duration - needed_duration

            if leftover_duration >= 30:
                # Keep remaining duration for victim
                cloned_victim.startTime = new_target_end.isoformat()
                cloned_victim.duration = leftover_duration
                candidate_sessions[i] = new_target_sess
                candidate_sessions.append(cloned_victim)
            else:
                # Replace completely
                candidate_sessions[i] = new_target_sess

            validation = validate_hard_constraints(candidate_sessions, all_tasks, fixed_events)
            if validation.valid:
                new_cand = schedule.model_copy()
                new_cand.sessions = candidate_sessions
                return new_cand

    return None

def try_shrink(
    schedule: CandidateSchedule,
    target_task: Task,
    all_tasks: List[Task],
    fixed_events: List[FixedEvent]
) -> Optional[CandidateSchedule]:
    sessions = sorted(
        [s.model_copy() for s in schedule.sessions],
        key=lambda x: parse_iso_datetime(x.startTime) or datetime.min
    )
    task_map = {t.id: t for t in all_tasks}
    target_urgency = target_task.effectiveUrgency or 30.0

    for i, sess in enumerate(sessions):
        t = task_map.get(sess.taskId)
        if not t:
            continue
        
        # If a lower-urgency session is 60m+ or 90m+, shrink by 30m
        if (t.effectiveUrgency or 30.0) < target_urgency and sess.duration >= 60:
            st = parse_iso_datetime(sess.startTime)
            if not st:
                continue

            # BUG #5 FIX: Deep copy candidate sessions
            candidate_sessions = [s.model_copy() for s in sessions]
            cloned_sess = candidate_sessions[i]
            
            # Shrink by 30 mins
            cloned_sess.duration -= 30
            cloned_sess.endTime = (st + timedelta(minutes=cloned_sess.duration)).isoformat()

            # Insert 30m session for target_task
            insert_start = parse_iso_datetime(cloned_sess.endTime)
            insert_end = insert_start + timedelta(minutes=30)
            new_sess = ScheduledSession(
                sessionId=f"repair_shrink_{target_task.id}_{len(candidate_sessions) + 1}",
                taskId=target_task.id,
                taskName=target_task.name,
                startTime=insert_start.isoformat(),
                endTime=insert_end.isoformat(),
                duration=30,
                contextType=target_task.contextType or "general",
                preferredTime=target_task.preferredTime
            )
            candidate_sessions.append(new_sess)

            validation = validate_hard_constraints(candidate_sessions, all_tasks, fixed_events)
            if validation.valid:
                new_cand = schedule.model_copy()
                new_cand.sessions = candidate_sessions
                return new_cand

    return None

def run_schedule_repair_engine(
    base_schedule: CandidateSchedule,
    all_tasks: List[Task],
    fixed_events: List[FixedEvent],
    user_pref: UserPreferences,
    max_attempts: int = 5,
    max_time_seconds: float = 2.0
) -> CandidateSchedule:
    current_schedule = base_schedule.model_copy()
    start_time = time.time()

    # Find unscheduled or starved tasks
    scheduled_task_ids = {s.taskId for s in current_schedule.sessions}
    unscheduled = [t for t in all_tasks if t.id not in scheduled_task_ids]
    # Sort unscheduled by urgency descending
    unscheduled.sort(key=lambda t: t.effectiveUrgency or 0.0, reverse=True)

    attempt = 0
    for target_task in unscheduled:
        # CONCERN #3 FIX: Guard against infinite or slow repair loops
        if attempt >= max_attempts or (time.time() - start_time) > max_time_seconds:
            break

        if (target_task.effectiveUrgency or 0.0) < 50.0 and not target_task.isStarved:
            continue

        attempt += 1

        # Try Move
        repaired = try_move(current_schedule, target_task, all_tasks, fixed_events)
        if repaired:
            current_schedule = evaluate_schedule(repaired, all_tasks, user_pref)
            continue

        # Try Swap
        repaired = try_swap(current_schedule, target_task, all_tasks, fixed_events)
        if repaired:
            current_schedule = evaluate_schedule(repaired, all_tasks, user_pref)
            continue

        # Try Shrink
        repaired = try_shrink(current_schedule, target_task, all_tasks, fixed_events)
        if repaired:
            current_schedule = evaluate_schedule(repaired, all_tasks, user_pref)
            continue

    return current_schedule
