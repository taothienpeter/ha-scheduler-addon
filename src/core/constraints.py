from datetime import datetime, timedelta, time
from typing import List, Dict, Tuple, Optional, Any
from src.models.schemas import Task, FixedEvent, UserPreferences, ScheduledSession, TimeSlot

def parse_iso_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        # Handle ISO strings with Z or timezone offsets
        clean_str = dt_str.replace("Z", "+00:00")
        return datetime.fromisoformat(clean_str)
    except Exception:
        try:
            return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S")
        except Exception:
            return None

class PlanningHorizon:
    def __init__(self, start_date: datetime, end_date: datetime, total_days: int):
        self.start_date = start_date
        self.end_date = end_date
        self.total_days = total_days

def build_planning_horizon(current_time: datetime, tasks: List[Task], max_days: int = 7) -> PlanningHorizon:
    # Normalize start to midnight of current day
    start_date = datetime(current_time.year, current_time.month, current_time.day, 0, 0, 0, tzinfo=current_time.tzinfo)
    
    max_deadline = start_date
    for t in tasks:
        if t.deadline:
            d_time = parse_iso_datetime(t.deadline)
            if d_time and d_time > max_deadline:
                max_deadline = d_time
                
    horizon_days = max(1, min(max_days, (max_deadline - start_date).days + 1))
    end_date = start_date + timedelta(days=horizon_days)
    return PlanningHorizon(start_date, end_date, horizon_days)

def compute_free_slots(
    horizon: PlanningHorizon,
    fixed_events: List[FixedEvent],
    user_pref: UserPreferences,
    current_time: datetime
) -> List[TimeSlot]:
    free_slots: List[TimeSlot] = []
    
    # Parse fixed events into datetime ranges
    parsed_events: List[Tuple[datetime, datetime]] = []
    for ev in fixed_events:
        if not ev.is_busy:
            continue
        ev_start = parse_iso_datetime(ev.startTime)
        ev_end = parse_iso_datetime(ev.endTime)
        if ev_start and ev_end and ev_end > ev_start:
            # Apply buffer time
            buf = timedelta(minutes=user_pref.buffer_time)
            parsed_events.append((ev_start - buf, ev_end + buf))

    work_start_m = user_pref.working_hours[0] if len(user_pref.working_hours) > 0 else 540
    work_end_m = user_pref.working_hours[1] if len(user_pref.working_hours) > 1 else 1020

    work_start_time = time(hour=work_start_m // 60, minute=work_start_m % 60)
    work_end_time = time(hour=work_end_m // 60, minute=work_end_m % 60)

    for day_offset in range(horizon.total_days):
        day_date = horizon.start_date + timedelta(days=day_offset)
        day_work_start = datetime.combine(day_date.date(), work_start_time, tzinfo=current_time.tzinfo)
        day_work_end = datetime.combine(day_date.date(), work_end_time, tzinfo=current_time.tzinfo)

        # Skip past times for today
        effective_start = max(day_work_start, current_time)
        if effective_start >= day_work_end:
            continue

        # Start with the whole working window for the day
        current_intervals: List[Tuple[datetime, datetime]] = [(effective_start, day_work_end)]

        # Subtract fixed events
        for ev_start, ev_end in parsed_events:
            next_intervals: List[Tuple[datetime, datetime]] = []
            for int_start, int_end in current_intervals:
                # Case 1: No overlap
                if ev_end <= int_start or ev_start >= int_end:
                    next_intervals.append((int_start, int_end))
                    continue
                # Case 2: Overlap left
                if ev_start > int_start:
                    next_intervals.append((int_start, min(ev_start, int_end)))
                # Case 3: Overlap right
                if ev_end < int_end:
                    next_intervals.append((max(ev_end, int_start), int_end))
            current_intervals = next_intervals

        # Filter slots >= 30 minutes
        for int_start, int_end in current_intervals:
            duration_m = int((int_end - int_start).total_seconds() // 60)
            if duration_m >= 30:
                free_slots.append(TimeSlot(startTime=int_start, endTime=int_end, duration=duration_m))

    return free_slots

class ValidationResult:
    def __init__(self, valid: bool, violations: List[str]):
        self.valid = valid
        self.violations = violations

    @property
    def is_valid(self) -> bool:
        return self.valid

def validate_hard_constraints(
    sessions: List[ScheduledSession],
    all_tasks: List[Task],
    fixed_events: List[FixedEvent]
) -> ValidationResult:
    violations: List[str] = []
    task_map: Dict[str, Task] = {t.id: t for t in all_tasks}

    # Parse and sort sessions by start time
    parsed_sessions: List[Dict[str, Any]] = []
    for s in sessions:
        st = parse_iso_datetime(s.startTime)
        et = parse_iso_datetime(s.endTime)
        if not st or not et or et <= st:
            violations.append(f"Session {s.sessionId} has invalid start/end timestamps.")
            continue
        parsed_sessions.append({
            "session": s,
            "start": st,
            "end": et,
            "duration": s.duration
        })

    # Constraint 1: Check Inter-Session Overlaps (No two sessions can overlap)
    parsed_sessions.sort(key=lambda x: x["start"])
    for i in range(len(parsed_sessions)):
        for j in range(i + 1, len(parsed_sessions)):
            s1 = parsed_sessions[i]
            s2 = parsed_sessions[j]
            if s1["end"] > s2["start"] and s1["start"] < s2["end"]:
                violations.append(
                    f"Conflict: Session {s1['session'].sessionId} ({s1['session'].taskName}) overlaps with {s2['session'].sessionId} ({s2['session'].taskName})"
                )

    # Constraint 2: Check Overlaps with Fixed Events
    parsed_fixed: List[Tuple[str, datetime, datetime]] = []
    for ev in fixed_events:
        if not ev.is_busy:
            continue
        st = parse_iso_datetime(ev.startTime)
        et = parse_iso_datetime(ev.endTime)
        if st and et:
            parsed_fixed.append((ev.name, st, et))

    for s_info in parsed_sessions:
        s_start = s_info["start"]
        s_end = s_info["end"]
        for ev_name, ev_start, ev_end in parsed_fixed:
            if max(s_start, ev_start) < min(s_end, ev_end):
                violations.append(
                    f"Conflict: Session {s_info['session'].sessionId} overlaps with Fixed Event '{ev_name}'."
                )

    # Constraint 3: Deadline Violations
    for s_info in parsed_sessions:
        task = task_map.get(s_info["session"].taskId)
        if task and task.deadline:
            d_time = parse_iso_datetime(task.deadline)
            if d_time and s_info["end"] > d_time:
                violations.append(
                    f"Deadline Violated: Session {s_info['session'].sessionId} ends at {s_info['end']} after deadline {d_time}."
                )

    # Constraint 4: Dependency Satisfaction
    # If Task B depends on Task A, Task B can only start after ALL of Task A is completed
    # (Total scheduled duration of A >= A.remaining_effort AND latest session of A <= earliest session of B)
    for task in all_tasks:
        if not task.dependencies:
            continue
        child_sessions = [s for s in parsed_sessions if s["session"].taskId == task.id]
        if not child_sessions:
            continue
        earliest_child_start = min(s["start"] for s in child_sessions)

        for dep_id in task.dependencies:
            dep_task = task_map.get(dep_id)
            if not dep_task:
                continue
            
            # If dependency is already completed historically
            if dep_task.status == "COMPLETED" or (dep_task.remaining_effort is not None and dep_task.remaining_effort <= 0):
                continue
                
            dep_sessions = [s for s in parsed_sessions if s["session"].taskId == dep_id]
            total_dep_scheduled = sum(s["duration"] for s in dep_sessions)
            needed_dep_effort = dep_task.remaining_effort if dep_task.remaining_effort is not None else dep_task.estimated_effort
            
            # Must complete 100% of dependency
            if total_dep_scheduled < needed_dep_effort:
                violations.append(
                    f"Dependency Unfulfilled: Task '{task.name}' starts but dependency '{dep_task.name}' is only scheduled for {total_dep_scheduled}/{needed_dep_effort} minutes."
                )
                continue
                
            latest_dep_end = max(s["end"] for s in dep_sessions)
            if latest_dep_end > earliest_child_start:
                violations.append(
                    f"Dependency Ordering Violated: Dependency '{dep_task.name}' finishes at {latest_dep_end}, which is after '{task.name}' starts at {earliest_child_start}."
                )

    return ValidationResult(valid=(len(violations) == 0), violations=violations)
