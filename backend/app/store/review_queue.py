"""人工审核队列内存存储（可替换为 Redis/DB）。"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any


@dataclass
class ReviewItem:
    meeting_id: str
    transcript_preview: str
    phase: str
    created_at: str
    state_snapshot: dict[str, Any]
    critic_report: dict[str, Any] = field(default_factory=dict)


class ReviewQueueStore:
    def __init__(self) -> None:
        self._items: dict[str, ReviewItem] = {}
        self._lock = Lock()

    def upsert(self, meeting_id: str, **kwargs: Any) -> ReviewItem:
        with self._lock:
            existing = self._items.get(meeting_id)
            if existing:
                for k, v in kwargs.items():
                    if hasattr(existing, k):
                        setattr(existing, k, v)
                    elif k == "state_snapshot":
                        existing.state_snapshot = v
                return existing
            item = ReviewItem(
                meeting_id=meeting_id,
                transcript_preview=kwargs.get("transcript_preview", "")[:200],
                phase=kwargs.get("phase", "awaiting_human"),
                created_at=datetime.now(timezone.utc).isoformat(),
                state_snapshot=kwargs.get("state_snapshot", {}),
                critic_report=kwargs.get("critic_report", {}),
            )
            self._items[meeting_id] = item
            return item

    def remove(self, meeting_id: str) -> None:
        with self._lock:
            self._items.pop(meeting_id, None)

    def list_pending(self) -> list[ReviewItem]:
        with self._lock:
            return [
                i
                for i in self._items.values()
                if i.phase in ("awaiting_human", "critiquing")
            ]

    def get(self, meeting_id: str) -> ReviewItem | None:
        with self._lock:
            return self._items.get(meeting_id)


review_queue = ReviewQueueStore()

# 流式事件订阅：meeting_id -> list[asyncio.Queue]
_event_subscribers: dict[str, list] = {}
