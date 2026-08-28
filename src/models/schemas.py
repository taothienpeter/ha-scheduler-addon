import math
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator

class Task(BaseModel):
    id: str = Field(..., min_length=1, description="Unique Task Identifier")
    name: str = Field(..., min_length=1, description="Task Name")
    estimated_effort: int = Field(..., gt=0, description="Estimated effort in minutes, must be > 0")
    remaining_effort: Optional[int] = Field(None, ge=0, description="Remaining effort in minutes")
    completed_effort: int = Field(0, ge=0, description="Completed effort in minutes")
    contextType: Optional[str] = "general" # coding, writing, reading, meeting, admin, creative, general
    deadline: Optional[str] = None # ISO format string
    dependencies: List[str] = Field(default_factory=list)
    status: str = "UNSCHEDULED" # UNSCHEDULED, SCHEDULED, PARTIAL, COMPLETED, DEFERRED
    deferral_count: int = Field(0, ge=0)
    priority: int = Field(3, ge=1, le=5, description="1 (Critical) to 5 (Lowest)")
    preferredTime: Optional[str] = None # 'morning', 'afternoon', 'evening'
    
    # Dynamic runtime attributes
    effectiveUrgency: Optional[float] = None
    slack_minutes: Optional[int] = None
    isStarved: bool = False
    starvationWarning: Optional[str] = None
    isSpanning: bool = False
    lastScheduledDuration: int = 0

    @field_validator("deadline")
    @classmethod
    def validate_deadline_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        try:
            clean = v.replace("Z", "+00:00")
            datetime.fromisoformat(clean)
            return v
        except Exception:
            raise ValueError(f"Invalid deadline datetime format: '{v}'. Must be ISO 8601 string.")

class FixedEvent(BaseModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    startTime: str # ISO format datetime
    endTime: str # ISO format datetime
    is_busy: bool = True

    @field_validator("startTime", "endTime")
    @classmethod
    def validate_iso_timestamps(cls, v: str) -> str:
        try:
            clean = v.replace("Z", "+00:00")
            datetime.fromisoformat(clean)
            return v
        except Exception:
            raise ValueError(f"Invalid event timestamp format: '{v}'. Must be ISO 8601 string.")

class TimeSlot(BaseModel):
    startTime: datetime
    endTime: datetime
    duration: int # in minutes

class ScheduledSession(BaseModel):
    sessionId: str
    taskId: str
    taskName: str
    startTime: str # ISO datetime string
    endTime: str # ISO datetime string
    duration: int = Field(..., gt=0) # minutes
    contextType: str = "general"
    preferredTime: Optional[str] = None
    isFrozen: bool = False

class ScoreBreakdown(BaseModel):
    completedWorkScore: float = 0.0
    tardinessPenalty: float = 0.0
    switchingCostPenalty: float = 0.0
    fragmentationPenalty: float = 0.0
    overloadPenalty: float = 0.0
    userPreferenceBonus: float = 0.0
    finalScore: float = 0.0

class CandidateSchedule(BaseModel):
    id: str
    strategyType: str = "DEFAULT"
    sessions: List[ScheduledSession] = Field(default_factory=list)
    remainingSlots: List[Dict[str, Any]] = Field(default_factory=list)
    scoreBreakdown: Optional[ScoreBreakdown] = None

class EnergyProfile(BaseModel):
    # 24-hour array (0..23) [0.0 - 1.0]
    hourlyEnergy: List[float] = Field(
        default_factory=lambda: [
            0.1, 0.1, 0.1, 0.1, 0.2, 0.4,
            0.6, 0.8, 0.95, 1.0, 0.9, 0.7,
            0.5, 0.6, 0.85, 0.8, 0.7, 0.6,
            0.5, 0.6, 0.7, 0.5, 0.3, 0.2
        ]
    )
    contextAffinities: Dict[str, List[float]] = Field(
        default_factory=lambda: {
            "coding": [
                0.1, 0.1, 0.1, 0.1, 0.2, 0.3,
                0.5, 0.8, 1.0, 1.0, 0.9, 0.6,
                0.4, 0.5, 0.8, 0.85, 0.7, 0.5,
                0.4, 0.5, 0.6, 0.4, 0.2, 0.1
            ],
            "writing": [
                0.1, 0.1, 0.1, 0.1, 0.2, 0.5,
                0.7, 0.9, 0.9, 0.8, 0.7, 0.6,
                0.5, 0.6, 0.7, 0.7, 0.6, 0.5,
                0.6, 0.7, 0.6, 0.4, 0.2, 0.1
            ],
            "meeting": [
                0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                0.1, 0.3, 0.6, 0.8, 0.9, 0.7,
                0.4, 0.7, 0.9, 0.9, 0.8, 0.5,
                0.3, 0.2, 0.1, 0.0, 0.0, 0.0
            ],
            "admin": [
                0.1, 0.1, 0.1, 0.1, 0.1, 0.2,
                0.3, 0.5, 0.6, 0.7, 0.7, 0.8,
                0.6, 0.7, 0.7, 0.7, 0.7, 0.6,
                0.5, 0.4, 0.3, 0.2, 0.1, 0.1
            ],
            "creative": [
                0.1, 0.1, 0.1, 0.1, 0.2, 0.4,
                0.6, 0.8, 0.9, 0.8, 0.7, 0.6,
                0.5, 0.6, 0.7, 0.8, 0.7, 0.6,
                0.7, 0.85, 0.9, 0.7, 0.4, 0.2
            ],
            "general": [
                0.2, 0.2, 0.2, 0.2, 0.3, 0.4,
                0.6, 0.7, 0.8, 0.8, 0.7, 0.6,
                0.5, 0.6, 0.7, 0.7, 0.6, 0.5,
                0.5, 0.5, 0.4, 0.3, 0.2, 0.2
            ]
        }
    )

class UserPreferences(BaseModel):
    timezone: str = "Asia/Ho_Chi_Minh"
    working_hours: List[int] = Field(default_factory=lambda: [540, 1020]) # 9:00 AM to 5:00 PM
    buffer_time: int = Field(15, ge=0) # minutes
    estimationBiasFactor: float = Field(1.15, gt=0.0)
    rescheduleThreshold: float = Field(0.10, ge=0.0, le=1.0) # 10% threshold
    frozenZoneHours: int = Field(3, ge=0)
    maxDeferralThreshold: int = Field(3, ge=1)
    weights: Dict[str, float] = Field(
        default_factory=lambda: {
            "wCompleted": 1.0,
            "wTardiness": 2.5,
            "wSwitching": 15.0,
            "wFragmentation": 20.0,
            "wOverload": 1.5,
            "wPreference": 10.0
        }
    )
    energyProfile: EnergyProfile = Field(default_factory=EnergyProfile)

    @field_validator("working_hours")
    @classmethod
    def validate_working_hours(cls, v: List[int]) -> List[int]:
        if len(v) != 2:
            raise ValueError("working_hours must contain exactly [start_minute, end_minute]")
        if not (0 <= v[0] < v[1] <= 1440):
            raise ValueError(f"working_hours {v} must satisfy 0 <= start < end <= 1440")
        return v

    @field_validator("weights")
    @classmethod
    def validate_weights(cls, v: Dict[str, float]) -> Dict[str, float]:
        for k, val in v.items():
            if not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val) or val < 0:
                raise ValueError(f"Weight '{k}' must be a non-negative finite number, got {val}")
        return v

class UserFeedbackEvent(BaseModel):
    eventType: str # 'TASK_COMPLETED', 'TASK_MOVED_BY_USER'
    taskId: str
    contextType: Optional[str] = "general"
    scheduledDuration: int = Field(..., gt=0)
    actualDuration: Optional[int] = Field(None, gt=0)
    newUserStartTime: Optional[str] = None
    timestamp: Optional[str] = None

class TaskExplanation(BaseModel):
    taskId: str
    taskName: str
    status: str
    scheduledDuration: int
    remainingEffort: int
    explanation: str
    energyMatch: str
    urgencyFactor: str
    conflictResolution: Optional[str] = None

class XAISummary(BaseModel):
    totalTasks: int
    completedCount: int
    partialCount: int
    deferredCount: int
    totalScheduledHours: float

class XAIReport(BaseModel):
    timestamp: str
    summary: XAISummary
    taskExplanations: List[TaskExplanation]
    insightsAndTips: List[str]

class ScheduleRequest(BaseModel):
    tasks: List[Task] = Field(..., min_length=1)
    fixedEvents: List[FixedEvent] = Field(default_factory=list)
    userPreferences: Optional[UserPreferences] = Field(default_factory=UserPreferences)
    current_time: Optional[str] = None # ISO format datetime (optional for testing/simulation)
    oldSchedule: Optional[List[ScheduledSession]] = None # Previous schedule to check stability
    recentFeedbackEvents: List[UserFeedbackEvent] = Field(default_factory=list)

class ScheduleResponse(BaseModel):
    success: bool
    sessions: List[ScheduledSession]
    updatedTasks: List[Task]
    score: Optional[float] = None
    scoreBreakdown: Optional[ScoreBreakdown] = None
    xaiReport: Optional[XAIReport] = None
    stabilityStatus: Optional[str] = None
    message: str = "Success"
