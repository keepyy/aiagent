"""审核队列 / 卡片展示用会议摘要。"""

from typing import Any

ACTION_TYPE_ZH = {
    "task": "任务",
    "decision": "决策",
    "follow_up": "跟进",
    "blocker": "阻塞",
}


def build_review_summary(
    state: dict[str, Any],
    critic_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """生成队列卡片展示字段（非最终人工结论，仅为机审+抽取摘要）。"""
    actions = state.get("action_items") or []
    utterances = state.get("utterances") or []
    todos = state.get("todos") or []
    report = critic_report or state.get("critic_report") or {}

    passed = bool(state.get("critic_passed") if state.get("critic_passed") is not None else report.get("passed"))
    score = report.get("score")
    issues = report.get("issues") or []

    action_previews: list[dict[str, str]] = []
    for a in actions[:6]:
        owner = (a.get("owner") or "未指定").strip()
        atype = ACTION_TYPE_ZH.get(a.get("action_type", ""), a.get("action_type", "任务"))
        title = (a.get("title") or "").strip()
        if len(title) > 42:
            title = title[:42] + "…"
        action_previews.append(
            {
                "owner": owner,
                "type": atype,
                "title": title,
                "due_date": a.get("due_date") or "",
            }
        )

    if action_previews:
        summary = "；".join(
            f"{p['owner']}({p['type']}): {p['title']}" for p in action_previews[:3]
        )
        if len(action_previews) > 3:
            summary += f" 等{len(action_previews)}项"
    elif utterances:
        first = utterances[0]
        summary = f"{first.get('speaker', '')}: {(first.get('text') or '')[:60]}"
    else:
        summary = (state.get("transcript") or "")[:80]

    metrics = report.get("metrics") or {}
    return {
        "summary": summary,
        "action_previews": action_previews,
        "utterance_count": metrics.get("utterance_count") or len(utterances),
        "todo_count": metrics.get("todo_count") or len(todos),
        "action_count": metrics.get("action_count") or len(actions),
        "critic_score": score,
        "critic_passed": passed,
        "critic_label": "机审通过" if passed else "机审未通过",
        "issue_count": len(issues),
        "human_status": "待人工审核",
    }
