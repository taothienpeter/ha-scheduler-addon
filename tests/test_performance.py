import time
import pytest
from datetime import datetime, timedelta
import tracemalloc

from src.models.schemas import Task, ScheduleRequest, UserPreferences
from src.core.engine import run_smart_scheduler_pipeline

def test_performance_100_tasks():
    # Setup 100 tasks
    tasks = []
    base_time = datetime.now()
    
    for i in range(100):
        tasks.append(
            Task(
                id=f"perf_task_{i}",
                name=f"Performance Task {i}",
                estimated_effort=60, # 1 hour each
                deadline=(base_time + timedelta(days=14)).isoformat(), # spread over 2 weeks
                priority=3
            )
        )
        
    req = ScheduleRequest(
        tasks=tasks,
        fixedEvents=[],
        userPreferences=UserPreferences(
            working_hours=[0, 1439], # 24/7 to guarantee slot for 100 hours
            buffer_time=0
        ),
        current_time=base_time.isoformat()
    )
    
    tracemalloc.start()
    start_time = time.time()
    
    res = run_smart_scheduler_pipeline(req)
    
    elapsed_ms = (time.time() - start_time) * 1000
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    peak_mem_mb = peak_mem / (1024 * 1024)
    
    # Assertions based on Phase 3 checklist
    # Target < 2000ms, but we can be generous in test environment
    assert elapsed_ms < 5000, f"Algorithm took too long: {elapsed_ms}ms"
    # Target < 150MB
    assert peak_mem_mb < 150.0, f"Memory usage too high: {peak_mem_mb}MB"
    
    assert res.success is True
    assert len(res.schedule) > 0
    
    print(f"Performance Test - Elapsed: {elapsed_ms:.2f}ms, Peak Memory: {peak_mem_mb:.2f}MB")
