"""SSE 事件总线（支持晚订阅回放，避免前端错过终态事件）。"""

import asyncio
from typing import Any

TERMINAL_TYPES = frozenset({"completed", "awaiting_human", "error", "finalized"})
MAX_BUFFER = 200


class EventBus:
    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue]] = {}
        self._buffers: dict[str, list[dict[str, Any]]] = {}

    def subscribe(self, meeting_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._queues.setdefault(meeting_id, []).append(q)
        return q

    def unsubscribe(self, meeting_id: str, queue: asyncio.Queue) -> None:
        subs = self._queues.get(meeting_id, [])
        if queue in subs:
            subs.remove(queue)
        if not subs:
            self._queues.pop(meeting_id, None)

    def get_replay(self, meeting_id: str) -> list[dict[str, Any]]:
        return list(self._buffers.get(meeting_id, []))

    def clear_meeting(self, meeting_id: str) -> None:
        self._buffers.pop(meeting_id, None)
        self._queues.pop(meeting_id, None)

    async def publish(self, meeting_id: str, event: dict[str, Any]) -> None:
        buf = self._buffers.setdefault(meeting_id, [])
        buf.append(event)
        if len(buf) > MAX_BUFFER:
            self._buffers[meeting_id] = buf[-MAX_BUFFER:]

        for q in list(self._queues.get(meeting_id, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass


event_bus = EventBus()
