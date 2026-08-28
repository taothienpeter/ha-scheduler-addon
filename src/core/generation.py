from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional, Any
from .models.schemas import Task, TimeSlot, ScheduledSession, CandidateSchedule
from .constraints import parse_iso_datetime

ALLOWED_DURATIONS = [120, 90, 60, 45, 30]

def generate_candidate_sessions(effort: int, max_combos: int = 5) -> List[List[int]]:
    """
    Tối ưu tổ hợp phiên làm việc bằng Greedy Chunking và Bounded Search.
    CONCERN #2 FIX: Thêm Depth Limit và Max Combos để chống đệ quy sâu/OOM.
    """
    if effort <= 0:
        return [[]]

    # For very large tasks (e.g. > 180 min), break down into 90m/120m standard chunks
    if effort >= 180:
        combo1 = []
        rem = effort
        while rem >= 120:
            combo1.append(120)
            rem -= 120
        if rem > 0:
            for d in ALLOWED_DURATIONS:
                if d <= rem:
                    combo1.append(d)
                    rem -= d
            if rem > 0:
                combo1.append(rem)

        combo2 = []
        rem = effort
        while rem >= 90:
            combo2.append(90)
            rem -= 90
        if rem > 0:
            for d in ALLOWED_DURATIONS:
                if d <= rem:
                    combo2.append(d)
                    rem -= d
            if rem > 0:
                combo2.append(rem)

        return [combo1, combo2]

    # For effort <= 180 min, find best exact or closest combinations
    results: List[List[int]] = []
    
    def backtrack(target: int, start_idx: int, current_path: List[int], depth: int):
        if depth > 20 or len(results) >= max_combos: # Strict bounds
            return
        if target == 0:
            results.append(list(current_path))
            return
        if target < 30:
            return

        for i in range(start_idx, len(ALLOWED_DURATIONS)):
            d = ALLOWED_DURATIONS[i]
            if d <= target:
                current_path.append(d)
                backtrack(target - d, i, current_path, depth + 1)
                current_path.pop()

    backtrack(effort, 0, [], 0)

    if not results:
        # Fallback: take largest chunk possible
        for d in ALLOWED_DURATIONS:
            if d <= effort:
                results.append([d])
                break
        if not results:
            results.append([effort])

    return results

def generate_strategy_candidates(competing_tasks: List[Task]) -> List[Dict[str, Any]]:
    if len(competing_tasks) < 2:
        return [{"type": "STANDARD", "sequence": [t.id for t in competing_tasks]}]

    task_a = competing_tasks[0]
    task_b = competing_tasks[1]

    effort_a = task_a.remaining_effort or task_a.estimated_effort
    effort_b = task_b.remaining_effort or task_b.estimated_effort

    count_a = max(1, (effort_a + 89) // 90)
    count_b = max(1, (effort_b + 89) // 90)

    candidates = []

    # 1. BATCH A -> B
    candidates.append({
        "type": "BATCH",
        "sequence": [task_a.id] * count_a + [task_b.id] * count_b
    })

    # 2. BATCH B -> A
    candidates.append({
        "type": "BATCH_REVERSE",
        "sequence": [task_b.id] * count_b + [task_a.id] * count_a
    })

    # 3. INTERLEAVE (A B A B...)
    interleave_seq = []
    max_len = max(count_a, count_b)
    for i in range(max_len):
        if i < count_a:
            interleave_seq.append(task_a.id)
        if i < count_b:
            interleave_seq.append(task_b.id)
            
    candidates.append({
        "type": "INTERLEAVE",
        "sequence": interleave_seq
    })

    return candidates

def build_schedule_from_sequence(
    task_ids: List[str],
    initial_slots: List[TimeSlot],
    task_map: Dict[str, Task],
    strategy_type: str
) -> CandidateSchedule:
    sessions: List[ScheduledSession] = []
    
    # Mutable copy of slots
    slots_copy = [
        {"startTime": s.startTime, "endTime": s.endTime, "duration": s.duration}
        for s in initial_slots
    ]

    remaining_map: Dict[str, int] = {}
    for tid in task_ids:
        if tid not in remaining_map:
            t = task_map.get(tid)
            remaining_map[tid] = (t.remaining_effort if t and t.remaining_effort is not None else (t.estimated_effort if t else 0))

    session_counter = 1

    for task_id in task_ids:
        task = task_map.get(task_id)
        if not task:
            continue

        needed = remaining_map.get(task_id, 0)
        if needed <= 0:
            continue

        combos = generate_candidate_sessions(needed)
        chosen_combo = combos[0] if combos else [min(needed, 90)]

        for target_duration in chosen_combo:
            if needed <= 0:
                break
            actual_duration = min(target_duration, needed)

            # Deadline constraint
            deadline_dt = parse_iso_datetime(task.deadline) if task.deadline else None

            # Find First-Fit slot
            slot_idx = -1
            for idx, slot in enumerate(slots_copy):
                if slot["duration"] >= actual_duration:
                    potential_end = slot["startTime"] + timedelta(minutes=actual_duration)
                    # Ensure session finishes before or on deadline
                    if deadline_dt is None or potential_end <= deadline_dt:
                        slot_idx = idx
                        break

            if slot_idx != -1:
                slot = slots_copy[slot_idx]
                sess_start = slot["startTime"]
                sess_end = sess_start + timedelta(minutes=actual_duration)

                sessions.append(ScheduledSession(
                    sessionId=f"sess_{task.id}_{session_counter}",
                    taskId=task.id,
                    taskName=task.name,
                    startTime=sess_start.isoformat(),
                    endTime=sess_end.isoformat(),
                    duration=actual_duration,
                    contextType=task.contextType or "general",
                    preferredTime=task.preferredTime
                ))
                session_counter += 1

                needed -= actual_duration
                remaining_map[task_id] = needed

                slot["duration"] -= actual_duration
                slot["startTime"] = sess_end

    remaining_slots = [
        {"startTime": s["startTime"].isoformat(), "endTime": s["endTime"].isoformat(), "duration": s["duration"]}
        for s in slots_copy if s["duration"] > 0
    ]

    return CandidateSchedule(
        id=f"schedule_{strategy_type.lower()}",
        strategyType=strategy_type,
        sessions=sessions,
        remainingSlots=remaining_slots
    )
