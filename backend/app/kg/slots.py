"""行动项知识图谱槽位定义与填充校验。"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    TASK = "task"
    DECISION = "decision"
    FOLLOW_UP = "follow_up"
    BLOCKER = "blocker"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class KGSlotSchema(BaseModel):
    """行动项在知识图谱中的标准槽位。"""

    action_id: str = Field(description="行动项唯一标识")
    action_type: ActionType = Field(description="行动类型")
    title: str = Field(description="行动摘要")
    owner: str | None = Field(default=None, description="责任人")
    due_date: str | None = Field(default=None, description="截止日期 ISO 或自然语言")
    priority: Priority = Field(default=Priority.MEDIUM)
    related_entities: list[str] = Field(
        default_factory=list, description="关联实体：项目/系统/人名等"
    )
    dependencies: list[str] = Field(
        default_factory=list, description="依赖的其他 action_id"
    )
    source_utterance_ids: list[str] = Field(
        default_factory=list, description="溯源发言片段"
    )
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)


REQUIRED_SLOTS = ("action_id", "action_type", "title")
OPTIONAL_SLOTS = (
    "owner",
    "due_date",
    "priority",
    "related_entities",
    "dependencies",
    "source_utterance_ids",
    "confidence",
)


def validate_slot_fill(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """校验槽位是否满足最低填充要求。"""
    errors: list[str] = []
    for key in REQUIRED_SLOTS:
        if not data.get(key):
            errors.append(f"缺少必填槽位: {key}")
    if data.get("confidence") is not None:
        c = data["confidence"]
        if not isinstance(c, (int, float)) or c < 0 or c > 1:
            errors.append("confidence 须在 [0,1]")
    return len(errors) == 0, errors


def slot_fill_score(data: dict[str, Any]) -> float:
    """槽位完整度得分，用于 Critic 评分。"""
    filled = sum(1 for k in KGSlotSchema.model_fields if data.get(k) not in (None, "", []))
    total = len(KGSlotSchema.model_fields)
    return round(filled / total, 2)
