from datetime import datetime
from typing import List, Dict, Tuple
from src.models.schemas import Task
from .constraints import parse_iso_datetime

PRIORITY_BASE_SCORES = {
    1: 50.0, # Critical
    2: 40.0, # High
    3: 30.0, # Medium
    4: 20.0, # Low
    5: 10.0  # Trivial
}

def calculate_dynamic_urgency(task: Task, current_time: datetime) -> Task:
    task_copy = task.model_copy()
    remaining = task_copy.remaining_effort if task_copy.remaining_effort is not None else task_copy.estimated_effort
    task_copy.remaining_effort = remaining

    base_score = PRIORITY_BASE_SCORES.get(task_copy.priority, 30.0)

    if not task_copy.deadline:
        task_copy.effectiveUrgency = base_score
        task_copy.slack_minutes = None
        return task_copy

    deadline_dt = parse_iso_datetime(task_copy.deadline)
    if not deadline_dt:
        task_copy.effectiveUrgency = base_score
        task_copy.slack_minutes = None
        return task_copy

    time_until_deadline = (deadline_dt - current_time).total_seconds() / 60.0
    slack = int(time_until_deadline - remaining)
    task_copy.slack_minutes = slack

    slack_bonus = 0.0
    if slack < 0:
        # Overdue or impossible without overtime
        slack_bonus = 200.0 + min(100.0, abs(slack) * 0.2)
    elif slack <= 120: # <= 2 hours
        slack_bonus = 100.0
    elif slack <= 360: # <= 6 hours
        slack_bonus = 60.0
    elif slack <= 1440: # <= 24 hours
        slack_bonus = 30.0
    elif slack <= 2880: # <= 48 hours
        slack_bonus = 15.0

    task_copy.effectiveUrgency = round(base_score + slack_bonus, 2)
    return task_copy

def apply_starvation_aging(tasks: List[Task], max_deferral_threshold: int = 3) -> List[Task]:
    aged_tasks: List[Task] = []
    for t in tasks:
        task = t.model_copy()
        deferrals = task.deferral_count or 0
        if deferrals > 0:
            # Non-linear boost: deferral_count^1.5 * 25, capped at 150
            aging_boost = min(150.0, (deferrals ** 1.5) * 25.0)
            is_starved = deferrals >= max_deferral_threshold
            current_urgency = task.effectiveUrgency if task.effectiveUrgency is not None else 30.0
            task.effectiveUrgency = round(current_urgency + aging_boost, 2)
            task.isStarved = is_starved
            if is_starved:
                task.starvationWarning = f"Task has been deferred {deferrals} times consecutively! Urgently prioritized."
        aged_tasks.append(task)
    return aged_tasks

class StrategyBuckets:
    def __init__(self):
        self.critical: List[Task] = []
        self.competition: List[Task] = []
        self.normal: List[Task] = []
        self.backlog: List[Task] = []

def classify_strategy_buckets(tasks: List[Task]) -> StrategyBuckets:
    buckets = StrategyBuckets()
    
    # Sort tasks descending by urgency
    sorted_tasks = sorted(tasks, key=lambda t: t.effectiveUrgency or 0.0, reverse=True)
    
    assigned = set()
    
    # 1. Critical Bucket: Starved or Urgency >= 100 or Slack <= 120
    for t in sorted_tasks:
        if t.isStarved or (t.effectiveUrgency and t.effectiveUrgency >= 100.0) or (t.slack_minutes is not None and t.slack_minutes <= 120):
            buckets.critical.append(t)
            assigned.add(t.id)

    # 2. Competition Bucket: Identify active non-critical tasks with close urgency and substantial duration
    remaining = [t for t in sorted_tasks if t.id not in assigned]
    
    competing = []
    if len(remaining) >= 2:
        for i in range(len(remaining) - 1):
            t1 = remaining[i]
            t2 = remaining[i + 1]
            diff = abs((t1.effectiveUrgency or 0.0) - (t2.effectiveUrgency or 0.0))
            if diff <= 15.0 and (t1.remaining_effort or 0) >= 60 and (t2.remaining_effort or 0) >= 60:
                if t1.id not in assigned:
                    competing.append(t1)
                    assigned.add(t1.id)
                if t2.id not in assigned:
                    competing.append(t2)
                    assigned.add(t2.id)
                if len(competing) >= 4: # Limit competition bucket size to avoid combinatorial blowup
                    break
    buckets.competition = competing

    # 3. Normal & Backlog Buckets
    for t in remaining:
        if t.id not in assigned:
            if t.slack_minutes is not None and t.slack_minutes > 4320 and t.priority >= 4: # > 3 days slack & low priority
                buckets.backlog.append(t)
            else:
                buckets.normal.append(t)
            assigned.add(t.id)

    return buckets
