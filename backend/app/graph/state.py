"""LangGraph 全局状态 — 贯穿 Plan / Executor / Critic / HITL。"""

from enum import Enum
from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class PipelinePhase(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    DIARIZING = "diarizing"
    EXTRACTING = "extracting"
    STRUCTURING = "structuring"
    CRITIQUING = "critiquing"
    AWAITING_HUMAN = "awaiting_human"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


class ReviewDecision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"


def merge_dicts(left: dict | None, right: dict | None) -> dict:
    base = dict(left or {})
    base.update(right or {})
    return base


class MeetingState(TypedDict, total=False):
    meeting_id: str
    transcript: str
    plan: dict[str, Any]
    utterances: list[dict[str, Any]]
    todos: list[dict[str, Any]]
    action_items: list[dict[str, Any]]
    critic_report: dict[str, Any]
    critic_passed: bool
    retry_count: int
    max_retries: int
    phase: str
    events: Annotated[list[dict[str, Any]], lambda a, b: (a or []) + (b or [])]
    messages: Annotated[list, add_messages]
    review_decision: str
    human_edits: dict[str, Any]
    error: str | None
