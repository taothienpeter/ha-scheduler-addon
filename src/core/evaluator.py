import math
from datetime import datetime
from typing import List, Dict, Optional, Any
from src.models.schemas import Task, ScheduledSession, CandidateSchedule, ScoreBreakdown, UserPreferences, EnergyProfile
from .constraints import parse_iso_datetime

def get_weight(weights: Dict[str, float], keys: List[str], default: float) -> float:
    for k in keys:
        if k in weights and weights[k] is not None:
            val = float(weights[k])
            if not math.isnan(val) and not math.isinf(val):
                return max(0.0, val)
    return default

def calculate_energy_bonus(session_dict: Dict[str, Any], task: Optional[Task], energy_prof: EnergyProfile) -> float:
    hour = session_dict["start"].hour
    ctx = session_dict["contextType"] or (task.contextType if task else "general") or "general"
    
    # 1. Base circadian energy at this hour (0.0 to 1.0)
    base_energy = 0.5
    if 0 <= hour < len(energy_prof.hourlyEnergy):
        base_energy = energy_prof.hourlyEnergy[hour]

    # 2. Context affinity at this hour (0.0 to 1.0)
    affinities = energy_prof.contextAffinities.get(ctx) or energy_prof.contextAffinities.get("general", [])
    context_affinity = 0.5
    if 0 <= hour < len(affinities):
        context_affinity = affinities[hour]

    # 3. Combined energy rating
    combined_energy = (base_energy + context_affinity) / 2.0
    return combined_energy * 20.0 # Scale to 0-20 points per session

def evaluate_schedule(
    schedule: CandidateSchedule,
    all_tasks: List[Task],
    user_pref: UserPreferences
) -> CandidateSchedule:
    task_map: Dict[str, Task] = {t.id: t for t in all_tasks}
    weights = user_pref.weights or {}
    
    # Support both camelCase and mathematical symbols (w_c, w_t, etc.)
    w_completed = get_weight(weights, ["wCompleted", "w_c"], 1.0)
    w_tardiness = get_weight(weights, ["wTardiness", "w_t"], 2.5)
    w_switching = get_weight(weights, ["wSwitching", "w_s"], 15.0)
    w_fragmentation = get_weight(weights, ["wFragmentation", "w_f"], 20.0)
    w_overload = get_weight(weights, ["wOverload", "w_o"], 1.5)
    w_preference = get_weight(weights, ["wPreference", "w_p"], 10.0)

    sessions = schedule.sessions or []
    remaining_slots = schedule.remainingSlots or []

    # 1. Parse and sort sessions chronologically by start time (CRITICAL FIX)
    parsed_sessions = []
    for s in sessions:
        st = parse_iso_datetime(s.startTime)
        et = parse_iso_datetime(s.endTime)
        if st and et:
            parsed_sessions.append({
                "session": s,
                "start": st,
                "end": et,
                "duration": s.duration,
                "taskId": s.taskId,
                "contextType": s.contextType,
                "preferredTime": s.preferredTime
            })
    parsed_sessions.sort(key=lambda x: x["start"])

    # 2. Completed Work Score
    total_minutes = sum(s["duration"] for s in parsed_sessions)
    completed_work_score = total_minutes * w_completed

    # 3. Tardiness Penalty
    tardiness_minutes = 0
    for s in parsed_sessions:
        task = task_map.get(s["taskId"])
        if task and task.deadline:
            d_time = parse_iso_datetime(task.deadline)
            if d_time and s["end"] > d_time:
                tardiness_minutes += int((s["end"] - d_time).total_seconds() // 60)
    tardiness_penalty = tardiness_minutes * w_tardiness

    # 4. Context Switching Penalty (Gap < 30m between different context types)
    switch_count = 0
    for i in range(1, len(parsed_sessions)):
        prev = parsed_sessions[i - 1]
        curr = parsed_sessions[i]
        if prev["contextType"] != curr["contextType"]:
            gap_m = int((curr["start"] - prev["end"]).total_seconds() // 60)
            if 0 <= gap_m < 30:
                switch_count += 1
    switching_cost_penalty = switch_count * w_switching

    # 5. Fragmentation Penalty (Remaining unused slots < 30 minutes)
    wasted_count = 0
    for slot in remaining_slots:
        dur = slot.get("duration", 0)
        if 0 < dur < 30:
            wasted_count += 1
    fragmentation_penalty = wasted_count * w_fragmentation

    # 6. Cognitive Overload Penalty (Continuous work > 240 mins without >= 15m break)
    overload_minutes = 0
    if len(parsed_sessions) > 0:
        continuous = parsed_sessions[0]["duration"]
        for i in range(1, len(parsed_sessions)):
            prev = parsed_sessions[i - 1]
            curr = parsed_sessions[i]
            gap_m = int((curr["start"] - prev["end"]).total_seconds() // 60)
            if 0 <= gap_m < 15:
                continuous += curr["duration"]
                if continuous > 240:
                    overload_minutes += (continuous - 240)
            else:
                continuous = curr["duration"]
    overload_penalty = overload_minutes * w_overload

    # 7. User Preference & Energy Match Bonus (Bug #8 Fix)
    pref_bonus = 0.0
    energy_prof = user_pref.energyProfile or EnergyProfile()
    for s in parsed_sessions:
        task = task_map.get(s["taskId"])
        pref_bonus += calculate_energy_bonus(s, task, energy_prof)

        # Additional static preferred time bonus
        hour = s["start"].hour
        pref = s["preferredTime"] or (task.preferredTime if task else None)
        if pref:
            if pref == "morning" and 6 <= hour < 12:
                pref_bonus += 10.0
            elif pref == "afternoon" and 12 <= hour < 18:
                pref_bonus += 10.0
            elif pref == "evening" and 18 <= hour < 22:
                pref_bonus += 10.0

    user_preference_bonus = round(pref_bonus * (w_preference / 10.0), 2)

    final_score = round(
        completed_work_score + user_preference_bonus
        - tardiness_penalty - switching_cost_penalty
        - fragmentation_penalty - overload_penalty,
        2
    )

    breakdown = ScoreBreakdown(
        completedWorkScore=round(completed_work_score, 2),
        tardinessPenalty=round(tardiness_penalty, 2),
        switchingCostPenalty=round(switching_cost_penalty, 2),
        fragmentationPenalty=round(fragmentation_penalty, 2),
        overloadPenalty=round(overload_penalty, 2),
        userPreferenceBonus=round(user_preference_bonus, 2),
        finalScore=final_score
    )

    schedule_copy = schedule.model_copy()
    schedule_copy.scoreBreakdown = breakdown
    # Retain sorted sessions
    schedule_copy.sessions = [s["session"] for s in parsed_sessions]
    return schedule_copy
