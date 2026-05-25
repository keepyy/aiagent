"""FastAPI：流式 SSE + 人工审核队列 + HITL resume。"""

import asyncio
import json
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.graph.workflow import get_graph, resume_after_human_review, run_until_interrupt
from app.store.events import event_bus
from app.store.review_queue import review_queue
from app.summary import build_review_summary

app = FastAPI(
    title="智能会议纪要 API",
    description="Plan-Executor-Critic + LangGraph HITL",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProcessRequest(BaseModel):
    transcript: str = Field(min_length=10, description="会议转写文本")
    max_retries: int = Field(default=2, ge=0, le=5)


class ReviewRequest(BaseModel):
    decision: str = Field(description="approved | rejected | edited")
    edits: dict[str, Any] | None = None


@app.get("/health")
async def health():
    return {"status": "ok", "framework": "langgraph"}


@app.post("/api/meetings/process")
async def process_meeting(body: ProcessRequest):
    meeting_id = str(uuid.uuid4())
    await event_bus.publish(
        meeting_id,
        {"type": "started", "meeting_id": meeting_id, "message": "流水线启动"},
    )

    async def _run():
        graph = get_graph()
        config = {"configurable": {"thread_id": meeting_id}}
        initial = {
            "meeting_id": meeting_id,
            "transcript": body.transcript,
            "retry_count": 0,
            "max_retries": body.max_retries,
            "phase": "idle",
            "review_decision": "pending",
        }
        try:
            async for chunk in graph.astream(initial, config=config, stream_mode="updates"):
                # LangGraph 在 HITL 中断时产出 __interrupt__（值为 tuple），需跳过
                if "__interrupt__" in chunk:
                    break
                for node_name, update in chunk.items():
                    if not isinstance(update, dict):
                        continue
                    events = update.get("events") or []
                    for ev in events:
                        payload = {
                            "type": "phase",
                            "meeting_id": meeting_id,
                            "node": node_name,
                            **ev,
                        }
                        await event_bus.publish(meeting_id, payload)
                    await event_bus.publish(
                        meeting_id,
                        {
                            "type": "state",
                            "meeting_id": meeting_id,
                            "node": node_name,
                            "phase": update.get("phase"),
                            "partial": {
                                k: update.get(k)
                                for k in (
                                    "plan",
                                    "utterances",
                                    "todos",
                                    "action_items",
                                    "critic_report",
                                    "critic_passed",
                                )
                                if update.get(k) is not None
                            },
                        },
                    )

            snapshot = await graph.aget_state(config)
            state = snapshot.values if snapshot else {}
            interrupted = bool(snapshot and snapshot.next)

            if interrupted or state.get("phase") == "awaiting_human":
                public = _public_state(state)
                public["phase"] = "awaiting_human"
                critic_report = state.get("critic_report") or {}
                meta = build_review_summary(public, critic_report)
                review_queue.upsert(
                    meeting_id,
                    transcript_preview=meta.get("summary") or body.transcript[:200],
                    phase="awaiting_human",
                    state_snapshot=public,
                    critic_report=critic_report,
                )
                await event_bus.publish(
                    meeting_id,
                    {
                        "type": "awaiting_human",
                        "meeting_id": meeting_id,
                        "message": "已进入人工审核队列",
                        "phase": "awaiting_human",
                        "state": public,
                    },
                )
            else:
                await event_bus.publish(
                    meeting_id,
                    {
                        "type": "completed",
                        "meeting_id": meeting_id,
                        "state": _public_state(state),
                    },
                )
        except Exception as e:
            logger.exception("meeting pipeline failed meeting_id=%s", meeting_id)
            await event_bus.publish(
                meeting_id,
                {"type": "app_error", "meeting_id": meeting_id, "message": str(e)},
            )

    async def _run_safe() -> None:
        try:
            await _run()
        except Exception:
            logger.exception("meeting pipeline task crashed meeting_id=%s", meeting_id)

    asyncio.create_task(_run_safe())
    return {"meeting_id": meeting_id, "stream_url": f"/api/meetings/{meeting_id}/stream"}


@app.get("/api/meetings/{meeting_id}/stream")
async def stream_meeting(meeting_id: str):
    queue = event_bus.subscribe(meeting_id)

    async def generator():
        try:
            yield {"event": "connected", "data": json.dumps({"meeting_id": meeting_id})}
            # 晚订阅回放：避免流水线过快完成导致前端收不到终态
            for past in event_bus.get_replay(meeting_id):
                yield {
                    "event": past.get("type", "message"),
                    "data": json.dumps(past, ensure_ascii=False),
                }
                if past.get("type") in ("completed", "awaiting_human", "error", "finalized"):
                    return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield {
                        "event": event.get("type", "message"),
                        "data": json.dumps(event, ensure_ascii=False),
                    }
                    if event.get("type") in (
                        "completed",
                        "awaiting_human",
                        "error",
                        "finalized",
                    ):
                        break
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            event_bus.unsubscribe(meeting_id, queue)

    return EventSourceResponse(generator())


@app.get("/api/meetings/{meeting_id}/state")
async def get_state(meeting_id: str):
    graph = get_graph()
    config = {"configurable": {"thread_id": meeting_id}}
    snapshot = await graph.aget_state(config)
    if not snapshot or not snapshot.values:
        item = review_queue.get(meeting_id)
        if item:
            return {"meeting_id": meeting_id, "state": item.state_snapshot}
        raise HTTPException(404, "会议不存在")
    return {
        "meeting_id": meeting_id,
        "state": _public_state(snapshot.values),
        "next": list(snapshot.next) if snapshot.next else [],
    }


@app.get("/api/meetings/{meeting_id}/pending")
async def meeting_pending(meeting_id: str):
    """前端用于判断当前会议是否仍可批准/驳回。"""
    graph = get_graph()
    config = {"configurable": {"thread_id": meeting_id}}
    snapshot = await graph.aget_state(config)
    values = snapshot.values if snapshot else {}
    nxt = list(snapshot.next) if snapshot and snapshot.next else []
    can_decide = bool(values.get("utterances")) and "human_review" in nxt
    if can_decide and not review_queue.get(meeting_id):
        public = _public_state(values)
        public["phase"] = "awaiting_human"
        critic_report = values.get("critic_report") or {}
        meta = build_review_summary(public, critic_report)
        review_queue.upsert(
            meeting_id,
            transcript_preview=meta.get("summary") or (values.get("transcript") or "")[:200],
            phase="awaiting_human",
            state_snapshot=public,
            critic_report=critic_report,
        )
    return {
        "meeting_id": meeting_id,
        "can_decide": can_decide,
        "next": nxt,
        "phase": values.get("phase"),
        "in_review_queue": review_queue.get(meeting_id) is not None,
    }


@app.get("/api/review-queue")
async def list_review_queue():
    items = review_queue.list_pending()
    result_items = []
    for i in items:
        snap = i.state_snapshot or {}
        meta = build_review_summary(snap, i.critic_report)
        result_items.append(
            {
                "meeting_id": i.meeting_id,
                "transcript_preview": i.transcript_preview,
                "phase": i.phase,
                "created_at": i.created_at,
                "critic_score": meta.get("critic_score"),
                "critic_passed": meta.get("critic_passed"),
                "critic_label": meta.get("critic_label"),
                "action_count": meta.get("action_count"),
                "todo_count": meta.get("todo_count"),
                "utterance_count": meta.get("utterance_count"),
                "summary": meta.get("summary"),
                "action_previews": meta.get("action_previews"),
                "human_status": meta.get("human_status"),
                "issue_count": meta.get("issue_count"),
            }
        )
    return {"count": len(result_items), "items": result_items}


@app.get("/api/review-queue/{meeting_id}")
async def get_review_item(meeting_id: str):
    item = review_queue.get(meeting_id)
    if not item:
        raise HTTPException(404, "不在审核队列中")
    snap = item.state_snapshot or {}
    return {
        "meeting_id": item.meeting_id,
        "state": _public_state(snap),
        "critic_report": item.critic_report,
        "review_summary": build_review_summary(snap, item.critic_report),
    }


async def _assert_can_resume(meeting_id: str) -> dict:
    """确认 LangGraph checkpoint 仍处于人工审核中断点。"""
    graph = get_graph()
    config = {"configurable": {"thread_id": meeting_id}}
    snapshot = await graph.aget_state(config)
    values = snapshot.values if snapshot else {}
    if not values or not values.get("utterances"):
        raise HTTPException(
            404,
            "会议状态不存在或已过期（后端重启后内存会清空，请重新运行流水线）",
        )
    nxt = tuple(snapshot.next or ())
    if "human_review" not in nxt:
        phase = values.get("phase") or ""
        if phase in ("approved", "rejected"):
            raise HTTPException(400, f"该会议已审核完成（{phase}），无需重复操作")
        raise HTTPException(400, "当前会议不在待人工审核状态")
    return values


@app.post("/api/review-queue/{meeting_id}/decide")
async def decide_review(meeting_id: str, body: ReviewRequest):
    if body.decision not in ("approved", "rejected", "edited"):
        raise HTTPException(400, "decision 须为 approved | rejected | edited")

    await _assert_can_resume(meeting_id)
    result = await resume_after_human_review(
        meeting_id, body.decision, body.edits
    )
    state = result.get("state") or {}
    if not state.get("meeting_id"):
        raise HTTPException(500, "审核恢复失败，请重试或重新运行流水线")
    review_queue.remove(meeting_id)

    await event_bus.publish(
        meeting_id,
        {
            "type": "finalized",
            "meeting_id": meeting_id,
            "decision": body.decision,
            "state": _public_state(state),
        },
    )
    return {
        "meeting_id": meeting_id,
        "decision": body.decision,
        "state": _public_state(state),
    }


def _public_state(state: dict) -> dict:
    return {
        "meeting_id": state.get("meeting_id"),
        "phase": state.get("phase"),
        "plan": state.get("plan"),
        "utterances": state.get("utterances"),
        "todos": state.get("todos"),
        "action_items": state.get("action_items"),
        "critic_report": state.get("critic_report"),
        "critic_passed": state.get("critic_passed"),
        "review_decision": state.get("review_decision"),
        "retry_count": state.get("retry_count"),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
