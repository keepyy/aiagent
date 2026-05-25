"""LangGraph 节点：Plan → Executor(s) → Critic → Human Review。"""

from typing import Any

from app.agents.critic import run_critic
from app.agents.executor import run_diarize, run_extract_todos, run_structure_actions
from app.agents.planner import run_planner
from app.graph.state import MeetingState, PipelinePhase, ReviewDecision


def _event(phase: str, message: str, payload: dict | None = None) -> dict[str, Any]:
    return {
        "events": [
            {
                "phase": phase,
                "message": message,
                "payload": payload or {},
            }
        ]
    }


async def planner_node(state: MeetingState) -> dict[str, Any]:
    transcript = state.get("transcript") or ""
    plan = await run_planner(transcript)
    return {
        "plan": plan,
        "phase": PipelinePhase.PLANNING.value,
        **_event(PipelinePhase.PLANNING.value, "Planner 已生成执行计划", {"plan": plan}),
    }


async def diarize_node(state: MeetingState) -> dict[str, Any]:
    transcript = state.get("transcript") or ""
    utterances = await run_diarize(transcript)
    return {
        "utterances": utterances,
        "phase": PipelinePhase.DIARIZING.value,
        **_event(
            PipelinePhase.DIARIZING.value,
            f"说话人分离完成，共 {len(utterances)} 段发言",
            {"count": len(utterances)},
        ),
    }


async def extract_node(state: MeetingState) -> dict[str, Any]:
    utterances = state.get("utterances") or []
    todos = await run_extract_todos(utterances)
    return {
        "todos": todos,
        "phase": PipelinePhase.EXTRACTING.value,
        **_event(
            PipelinePhase.EXTRACTING.value,
            f"待办抽取完成，共 {len(todos)} 条",
            {"count": len(todos)},
        ),
    }


async def structure_node(state: MeetingState) -> dict[str, Any]:
    todos = state.get("todos") or []
    utterances = state.get("utterances") or []
    actions = await run_structure_actions(todos, utterances)
    return {
        "action_items": actions,
        "phase": PipelinePhase.STRUCTURING.value,
        **_event(
            PipelinePhase.STRUCTURING.value,
            f"行动项 KG 结构化完成，共 {len(actions)} 条",
            {"count": len(actions)},
        ),
    }


async def critic_node(state: MeetingState) -> dict[str, Any]:
    report = await run_critic(dict(state))
    passed = bool(report.get("passed"))
    retry = int(state.get("retry_count") or 0)
    return {
        "critic_report": report,
        "critic_passed": passed,
        "phase": PipelinePhase.CRITIQUING.value,
        **_event(
            PipelinePhase.CRITIQUING.value,
            "Critic 评审完成",
            {"passed": passed, "report": report},
        ),
        "retry_count": retry + (0 if passed else 1),
    }


async def human_review_node(state: MeetingState) -> dict[str, Any]:
    """进入人工审核队列；LangGraph interrupt 在此节点前触发。"""
    return {
        "phase": PipelinePhase.AWAITING_HUMAN.value,
        "review_decision": ReviewDecision.PENDING.value,
        **_event(
            PipelinePhase.AWAITING_HUMAN.value,
            "等待人工审核（Human-in-the-loop）",
            {
                "utterances": len(state.get("utterances") or []),
                "todos": len(state.get("todos") or []),
                "actions": len(state.get("action_items") or []),
            },
        ),
    }


async def finalize_node(state: MeetingState) -> dict[str, Any]:
    decision = state.get("review_decision") or ReviewDecision.APPROVED.value
    phase = (
        PipelinePhase.APPROVED.value
        if decision in (ReviewDecision.APPROVED.value, ReviewDecision.EDITED.value)
        else PipelinePhase.REJECTED.value
    )
    edits = state.get("human_edits") or {}
    patch: dict[str, Any] = {"phase": phase, "review_decision": decision}
    if edits.get("action_items"):
        patch["action_items"] = edits["action_items"]
    if edits.get("todos"):
        patch["todos"] = edits["todos"]
    return {
        **patch,
        **_event(phase, f"人工审核结束：{decision}"),
    }
