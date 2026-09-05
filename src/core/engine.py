import time
from datetime import datetime
from typing import List, Dict, Optional, Any
from src.models.schemas import (
    ScheduleRequest, ScheduleResponse, Task, CandidateSchedule,
    ScheduledSession, UserPreferences, PipelineTrace
)
from .constraints import (
    parse_iso_datetime, build_planning_horizon, compute_free_slots,
    validate_hard_constraints
)
from .urgency import (
    calculate_dynamic_urgency, apply_starvation_aging, classify_strategy_buckets
)
from .generation import (
    generate_strategy_candidates, build_schedule_from_sequence
)
from .evaluator import evaluate_schedule
from .repair import run_schedule_repair_engine
from .local_search import (
    run_limited_local_search, check_schedule_stability, partition_time_fences
)
from .spanning import (
    apply_stateful_spanning, update_estimation_bias, generate_xai_report
)

def run_smart_scheduler_pipeline(request: ScheduleRequest) -> ScheduleResponse:
    start_perf = time.time()
    # Step 1: Normalize current time
    current_time = parse_iso_datetime(request.current_time) if request.current_time else datetime.now()
    if not current_time:
        current_time = datetime.now()

    user_pref = request.userPreferences or UserPreferences()

    # Step 2: Adaptive Learning from Feedback (Estimation Bias)
    if request.recentFeedbackEvents:
        user_pref = update_estimation_bias(user_pref, request.recentFeedbackEvents)

    if not request.tasks:
        return ScheduleResponse(
            success=True,
            sessions=[],
            updatedTasks=[],
            score=0.0,
            pipelineTrace=PipelineTrace(elapsedSeconds=round(time.time() - start_perf, 3)),
            message="No tasks provided to schedule."
        )

    # Step 3: Dynamic Urgency & Starvation Aging
    tasks = [calculate_dynamic_urgency(t, current_time) for t in request.tasks]
    tasks = apply_starvation_aging(tasks, user_pref.maxDeferralThreshold or 3)
    task_map = {t.id: t for t in tasks}

    # Step 4: Build Horizon & Compute Free Slots
    horizon = build_planning_horizon(current_time, tasks, max_days=7)
    free_slots = compute_free_slots(horizon, request.fixedEvents, user_pref, current_time)

    if not free_slots:
        # No free slots available at all
        updated_tasks = apply_stateful_spanning(CandidateSchedule(id="empty"), tasks)
        xai_report = generate_xai_report(CandidateSchedule(id="empty"), updated_tasks, user_pref)
        return ScheduleResponse(
            success=True,
            sessions=[],
            updatedTasks=updated_tasks,
            score=0.0,
            xaiReport=xai_report,
            pipelineTrace=PipelineTrace(
                horizonStart=horizon.start_date.isoformat(),
                horizonEnd=horizon.end_date.isoformat(),
                freeSlotsCount=0,
                totalFreeMinutes=0,
                elapsedSeconds=round(time.time() - start_perf, 3)
            ),
            message="No available free slots in planning horizon."
        )

    # Step 5: Classify Tasks into Strategy Buckets
    buckets = classify_strategy_buckets(tasks)

    # Step 6: Generate Candidate Scenarios
    candidate_scenarios: List[CandidateSchedule] = []

    if len(buckets.competition) >= 2:
        strategies = generate_strategy_candidates(buckets.competition)
        for idx, strat in enumerate(strategies):
            full_seq = [t.id for t in buckets.critical] + strat["sequence"] + [t.id for t in buckets.normal]
            sc = build_schedule_from_sequence(full_seq, free_slots, task_map, strat["type"])
            candidate_scenarios.append(sc)
    else:
        all_active = buckets.critical + buckets.competition + buckets.normal
        sc = build_schedule_from_sequence([t.id for t in all_active], free_slots, task_map, "FLEXIBLE_GREEDY")
        candidate_scenarios.append(sc)

    # Step 7: Global Evaluation of Candidates
    evaluated_scenarios = [evaluate_schedule(sc, tasks, user_pref) for sc in candidate_scenarios]
    evaluated_scenarios.sort(
        key=lambda sc: sc.scoreBreakdown.finalScore if sc.scoreBreakdown else -9999.0,
        reverse=True
    )
    best_candidate = evaluated_scenarios[0]
    initial_score = best_candidate.scoreBreakdown.finalScore if best_candidate.scoreBreakdown else 0.0

    # Step 8: Repair Engine
    repaired_schedule = run_schedule_repair_engine(best_candidate, tasks, request.fixedEvents, user_pref)
    repair_count = sum(1 for s in repaired_schedule.sessions if s.sessionId and s.sessionId.startswith("repair_"))

    # Step 9: Time Fencing & Limited Local Search
    repaired_schedule.sessions = partition_time_fences(
        repaired_schedule.sessions,
        current_time,
        user_pref.frozenZoneHours or 3
    )
    score_before_search = repaired_schedule.scoreBreakdown.finalScore if repaired_schedule.scoreBreakdown else initial_score
    optimized_schedule = run_limited_local_search(
        repaired_schedule,
        tasks,
        request.fixedEvents,
        user_pref,
        max_iterations=50
    )
    score_after_search = optimized_schedule.scoreBreakdown.finalScore if optimized_schedule.scoreBreakdown else score_before_search
    swaps_improved = 1 if score_after_search > score_before_search else 0

    # Step 10: Stability Guard Check (Schedule Nervousness Prevention)
    stability_res = check_schedule_stability(
        optimized_schedule,
        request.oldSchedule,
        tasks,
        request.fixedEvents,
        current_time,
        user_pref
    )

    committed_schedule = optimized_schedule if stability_res.should_update else CandidateSchedule(
        id="retained_old",
        sessions=request.oldSchedule or []
    )
    committed_schedule = evaluate_schedule(committed_schedule, tasks, user_pref)

    # Step 11: Stateful Spanning & State Transitions
    updated_tasks = apply_stateful_spanning(committed_schedule, tasks)

    # Step 12: Explainable AI Report
    xai_report = generate_xai_report(committed_schedule, updated_tasks, user_pref)

    stability_msg = (
        f"Committed new schedule (Reason: {stability_res.reason}, Improvement: {stability_res.improvement_rate}%)"
        if stability_res.should_update
        else f"Retained existing schedule to avoid nervousness (Improvement {stability_res.improvement_rate}% < threshold {user_pref.rescheduleThreshold * 100}%)"
    )

    final_score = committed_schedule.scoreBreakdown.finalScore if committed_schedule.scoreBreakdown else 0.0
    elapsed_total = round(time.time() - start_perf, 3)

    trace = PipelineTrace(
        horizonStart=horizon.start_date.isoformat(),
        horizonEnd=horizon.end_date.isoformat(),
        freeSlotsCount=len(free_slots),
        totalFreeMinutes=sum(s.duration for s in free_slots),
        strategyBuckets={
            "critical": [getattr(t, "name", t.id) for t in buckets.critical],
            "competition": [getattr(t, "name", t.id) for t in buckets.competition],
            "normal": [getattr(t, "name", t.id) for t in buckets.normal]
        },
        candidatesEvaluatedCount=len(candidate_scenarios),
        repairsApplied=repair_count,
        localSearchSwaps=swaps_improved,
        stabilityImprovementRate=stability_res.improvement_rate,
        stabilityAction="COMMITTED" if stability_res.should_update else "RETAINED",
        initialScore=initial_score,
        finalScore=final_score,
        elapsedSeconds=elapsed_total
    )

    return ScheduleResponse(
        success=True,
        sessions=committed_schedule.sessions,
        updatedTasks=updated_tasks,
        score=final_score,
        scoreBreakdown=committed_schedule.scoreBreakdown,
        xaiReport=xai_report,
        stabilityStatus=stability_msg,
        pipelineTrace=trace,
        message="Optimization pipeline finished successfully."
    )

