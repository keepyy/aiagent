"""LangGraph Plan-Executor-Critic + Human-in-the-loop 工作流。"""

from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from app.graph.nodes import (
    critic_node,
    diarize_node,
    extract_node,
    finalize_node,
    human_review_node,
    planner_node,
    structure_node,
)
from app.graph.state import MeetingState, PipelinePhase

_checkpointer = MemorySaver()
_compiled_graph = None


def _route_after_critic(state: MeetingState) -> Literal["human_review", "diarize", "extract", "structure", "failed"]:
    if state.get("critic_passed"):
        return "human_review"
    retry = int(state.get("retry_count") or 0)
    max_retries = int(state.get("max_retries") or 2)
    if retry > max_retries:
        return "failed"
    target = (state.get("critic_report") or {}).get("retry_target") or "structure"
    return target  # type: ignore[return-value]


def build_meeting_graph():
    g = StateGraph(MeetingState)

    g.add_node("planner", planner_node)
    g.add_node("diarize", diarize_node)
    g.add_node("extract", extract_node)
    g.add_node("structure", structure_node)
    g.add_node("critic", critic_node)
    g.add_node("human_review", human_review_node)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "planner")
    g.add_edge("planner", "diarize")
    g.add_edge("diarize", "extract")
    g.add_edge("extract", "structure")
    g.add_edge("structure", "critic")

    g.add_conditional_edges(
        "critic",
        _route_after_critic,
        {
            "human_review": "human_review",
            "diarize": "diarize",
            "extract": "extract",
            "structure": "structure",
            "failed": END,
        },
    )

    # human_review 后由 API resume 进入 finalize
    g.add_edge("human_review", "finalize")
    g.add_edge("finalize", END)

    return g.compile(
        checkpointer=_checkpointer,
        interrupt_before=["human_review"],
    )


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_meeting_graph()
    return _compiled_graph


async def run_until_interrupt(
    meeting_id: str,
    transcript: str,
    max_retries: int = 2,
) -> dict:
    graph = get_graph()
    config = {"configurable": {"thread_id": meeting_id}}
    initial: MeetingState = {
        "meeting_id": meeting_id,
        "transcript": transcript,
        "retry_count": 0,
        "max_retries": max_retries,
        "phase": PipelinePhase.IDLE.value,
        "review_decision": "pending",
    }
    result = None
    async for event in graph.astream(initial, config=config, stream_mode="updates"):
        result = event
    snapshot = await graph.aget_state(config)
    return {
        "updates": result,
        "state": snapshot.values if snapshot else {},
        "next": snapshot.next if snapshot else (),
        "interrupted": bool(snapshot and snapshot.next),
    }


async def resume_after_human_review(
    meeting_id: str,
    decision: str,
    edits: dict | None = None,
) -> dict:
    graph = get_graph()
    config = {"configurable": {"thread_id": meeting_id}}
    resume_payload = {
        "review_decision": decision,
        "human_edits": edits or {},
    }
    # 消费 interrupt：传入人工决策
    await graph.aupdate_state(config, resume_payload, as_node="human_review")
    async for chunk in graph.astream(None, config=config, stream_mode="updates"):
        if "__interrupt__" in chunk:
            break
    snapshot = await graph.aget_state(config)
    return {
        "state": snapshot.values if snapshot else {},
        "phase": (snapshot.values or {}).get("phase"),
    }
