"""Critic Agent：质量门禁，不通过则打回 Executor 重试。"""

from typing import Any

from app.kg.slots import slot_fill_score, validate_slot_fill
from app.llm import ainvoke_json


CRITIC_SYSTEM = """你是会议纪要质量评审 Critic。输出 JSON：
{
  "passed": true,
  "score": 0.9,
  "issues": [{"severity": "warning", "target": "action_items", "message": "..."}],
  "retry_target": null
}
passed=false 时 retry_target 为 diarize|extract|structure 之一。仅 JSON。"""


async def run_critic(state: dict[str, Any]) -> dict[str, Any]:
    utterances = state.get("utterances") or []
    todos = state.get("todos") or []
    actions = state.get("action_items") or []

    rule_issues: list[dict[str, str]] = []
    if len(utterances) < 1:
        rule_issues.append(
            {
                "severity": "error",
                "target": "utterances",
                "message": "说话人分离结果为空",
            }
        )
    if len(todos) < 1:
        rule_issues.append(
            {"severity": "warning", "target": "todos", "message": "未抽取到待办项"}
        )

    slot_scores = []
    invalid_actions = 0
    for a in actions:
        ok, errs = validate_slot_fill(a)
        if not ok:
            invalid_actions += 1
            rule_issues.append(
                {
                    "severity": "error",
                    "target": a.get("action_id", "action"),
                    "message": "; ".join(errs),
                }
            )
        slot_scores.append(slot_fill_score(a))

    avg_slot = sum(slot_scores) / len(slot_scores) if slot_scores else 0.0
    rule_score = 1.0
    if not utterances:
        rule_score -= 0.4
    if not todos:
        rule_score -= 0.15
    if invalid_actions:
        rule_score -= 0.2 * invalid_actions
    rule_score = max(0.0, min(1.0, rule_score * 0.6 + avg_slot * 0.4))

    passed = rule_score >= 0.65 and len(utterances) >= 1 and invalid_actions == 0
    retry_target = None
    if not passed:
        if not utterances:
            retry_target = "diarize"
        elif not todos:
            retry_target = "extract"
        else:
            retry_target = "structure"

    mock = {
        "passed": passed,
        "score": round(rule_score, 2),
        "issues": rule_issues,
        "retry_target": retry_target if not passed else None,
        "metrics": {
            "utterance_count": len(utterances),
            "todo_count": len(todos),
            "action_count": len(actions),
            "avg_slot_fill": round(avg_slot, 2),
        },
    }

    if not state.get("_skip_llm_critic"):
        llm_report = await ainvoke_json(
            CRITIC_SYSTEM,
            f"评审数据：{mock}",
            mock=mock,
        )
        mock.update({k: v for k, v in llm_report.items() if k in mock or k == "passed"})
        if "passed" in llm_report:
            mock["passed"] = bool(llm_report["passed"]) and passed

    return mock
