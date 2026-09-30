from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
from src.models.schemas import (
    Task, ScheduledSession, CandidateSchedule, UserPreferences,
    UserFeedbackEvent, XAIReport, XAISummary, TaskExplanation, EnergyProfile
)
from .constraints import parse_iso_datetime, resolve_timezone

def apply_stateful_spanning(
    schedule: CandidateSchedule,
    raw_tasks: List[Task],
    current_time: Optional[datetime] = None
) -> List[Task]:
    sessions = schedule.sessions or []
    
    # Calculate scheduled duration per task in this cycle
    scheduled_map: Dict[str, int] = {}
    for s in sessions:
        scheduled_map[s.taskId] = scheduled_map.get(s.taskId, 0) + s.duration

    target_tz = (current_time.tzinfo if current_time else None) or resolve_timezone()
    now_dt = current_time or datetime.now().astimezone(target_tz)

    updated_tasks: List[Task] = []
    for task in raw_tasks:
        t = task.model_copy()
        scheduled_mins = scheduled_map.get(t.id, 0)
        
        initial_remaining = t.remaining_effort if t.remaining_effort is not None else t.estimated_effort
        current_completed = t.completed_effort or 0

        new_completed = current_completed + scheduled_mins
        new_remaining = max(0, initial_remaining - scheduled_mins)

        t.lastScheduledDuration = scheduled_mins
        t.completed_effort = new_completed
        t.remaining_effort = new_remaining

        # Check deadline vs now_dt
        deadline_dt = parse_iso_datetime(t.deadline, target_tz=target_tz) if t.deadline else None
        is_deadline_passed = bool(deadline_dt and deadline_dt < now_dt)

        if new_remaining == 0:
            t.status = "COMPLETED"
            t.deferral_count = 0
            t.isSpanning = False
        elif is_deadline_passed:
            t.status = "OVERDUE"
            t.isSpanning = False
            if scheduled_mins == 0:
                t.deferral_count = (t.deferral_count or 0) + 1
        elif scheduled_mins == 0:
            t.status = "DEFERRED"
            t.deferral_count = (t.deferral_count or 0) + 1
            t.isSpanning = False
        else:
            t.status = "PARTIAL"
            t.deferral_count = 0
            t.isSpanning = True

        updated_tasks.append(t)

    return updated_tasks

def update_estimation_bias(
    user_pref: UserPreferences,
    feedback_events: List[UserFeedbackEvent],
    learning_rate: float = 0.15
) -> UserPreferences:
    pref_copy = user_pref.model_copy()
    current_factor = pref_copy.estimationBiasFactor or 1.15

    for ev in feedback_events:
        if ev.eventType == "TASK_COMPLETED" and ev.actualDuration and ev.scheduledDuration:
            if ev.scheduledDuration > 0:
                observed_ratio = ev.actualDuration / float(ev.scheduledDuration)
                clamped_ratio = max(0.5, min(3.0, observed_ratio))
                current_factor = (1.0 - learning_rate) * current_factor + learning_rate * clamped_ratio

    pref_copy.estimationBiasFactor = round(current_factor, 3)
    return pref_copy

def generate_xai_report(
    committed_schedule: CandidateSchedule,
    updated_tasks: List[Task],
    user_pref: UserPreferences,
    current_time: Optional[datetime] = None
) -> XAIReport:
    sessions = committed_schedule.sessions or []
    completed_tasks = [t for t in updated_tasks if t.status == "COMPLETED"]
    partial_tasks = [t for t in updated_tasks if t.status == "PARTIAL"]
    deferred_tasks = [t for t in updated_tasks if t.status == "DEFERRED"]
    overdue_tasks = [t for t in updated_tasks if t.status == "OVERDUE"]

    total_scheduled_minutes = sum(s.duration for s in sessions)
    energy_prof = user_pref.energyProfile or EnergyProfile()

    task_explanations: List[TaskExplanation] = []
    for task in updated_tasks:
        task_sessions = [s for s in sessions if s.taskId == task.id]
        scheduled_minutes = sum(s.duration for s in task_sessions)

        energy_match_str = "Standard"
        urgency_str = f"Urgency: {task.effectiveUrgency if task.effectiveUrgency is not None else task.priority}"
        conflict_res = None
        explanation = ""

        if task.status == "COMPLETED":
            if len(task_sessions) == 1:
                target_tz = resolve_timezone(user_pref.timezone if user_pref else None)
                st = parse_iso_datetime(task_sessions[0].startTime, target_tz=target_tz)
                start_hour = st.hour if st else 9
                ctx = task.contextType or "general"
                affinities = energy_prof.contextAffinities.get(ctx) or energy_prof.contextAffinities.get("general", [])
                affinity = affinities[start_hour] if 0 <= start_hour < len(affinities) else 0.5
                if affinity >= 0.8:
                    energy_match_str = f"Optimal (Peak focus at {start_hour}:00)"
                    explanation = f"Allocated all {scheduled_minutes}m into your highest productivity window for [{ctx}]."
                else:
                    explanation = f"Allocated all {scheduled_minutes}m into available free time."
            else:
                durations_str = ", ".join([f"{s.duration}m" for s in task_sessions])
                explanation = f"Split into {len(task_sessions)} sessions ({durations_str}) to comfortably fit slots without fatigue."
        elif task.status == "PARTIAL":
            explanation = f"Allocated {scheduled_minutes}m today. {task.remaining_effort}m remaining will automatically continue in next day's schedule."
            conflict_res = "Stateful Spanning applied to preserve momentum before deadline."
        elif task.status == "OVERDUE":
            d_str = task.deadline or "in the past"
            explanation = f"Deadline has expired ({d_str}). Cannot schedule into future slots due to hard deadline constraint."
            conflict_res = "Immediate action needed: extend deadline or adjust task priority/effort."
        elif task.status == "DEFERRED":
            explanation = "Postponed to next cycle because higher dynamic urgency tasks occupied available daily slots."
            conflict_res = f"Priority increased (Deferral count: {task.deferral_count}) to prevent starvation in next run."

        task_explanations.append(TaskExplanation(
            taskId=task.id,
            taskName=task.name,
            status=task.status,
            scheduledDuration=scheduled_minutes,
            remainingEffort=task.remaining_effort or 0,
            explanation=explanation,
            energyMatch=energy_match_str,
            urgencyFactor=urgency_str,
            conflictResolution=conflict_res
        ))

    # Insights & Tips
    insights_and_tips: List[str] = []
    if len(overdue_tasks) > 0:
        insights_and_tips.append(
            f"🚨 You have {len(overdue_tasks)} overdue task(s). Review deadlines or resolve them to prevent backlog pileup."
        )
    if len(partial_tasks) > 0:
        insights_and_tips.append(
            f"💡 You have {len(partial_tasks)} multi-day spanning task(s). Focus on making steady progress!"
        )
    if total_scheduled_minutes > 360:
        insights_and_tips.append(
            f"⚠️ Total planned work today is {round(total_scheduled_minutes / 60.0, 1)} hours. Remember to take breaks!"
        )
    if user_pref.estimationBiasFactor and user_pref.estimationBiasFactor > 1.25:
        pct = round((user_pref.estimationBiasFactor - 1.0) * 100)
        insights_and_tips.append(
            f"📈 Feedback insight: You typically need ~{pct}% more time than initial estimates. Auto-adjusting buffers."
        )

    summary = XAISummary(
        totalTasks=len(updated_tasks),
        completedCount=len(completed_tasks),
        partialCount=len(partial_tasks),
        deferredCount=len(deferred_tasks),
        overdueCount=len(overdue_tasks),
        totalScheduledHours=round(total_scheduled_minutes / 60.0, 1)
    )

    target_tz = resolve_timezone(user_pref.timezone if user_pref else None)
    return XAIReport(
        timestamp=(current_time or datetime.now().astimezone(target_tz)).isoformat(),
        summary=summary,
        taskExplanations=task_explanations,
        insightsAndTips=insights_and_tips
    )
