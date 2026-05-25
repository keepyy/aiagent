"""Executor Agents：说话人分离、待办抽取、行动项 KG 结构化。"""

import re
import uuid
from typing import Any

from app.kg.slots import ActionType, Priority, validate_slot_fill
from app.llm import ainvoke_json


DIARIZE_SYSTEM = """你是说话人分离专家。输出 JSON：
{"utterances": [{"id": "u1", "speaker": "Speaker A", "text": "...", "start_offset": 0}]}
按行或说话人标记切分。仅 JSON。"""

EXTRACT_SYSTEM = """你是待办抽取专家。输出 JSON：
{"todos": [{"id": "t1", "text": "...", "assignee": null, "deadline": null, "utterance_id": "u1"}]}
仅 JSON。"""

STRUCTURE_SYSTEM = """你是行动项结构化专家。为每条待办填充知识图谱槽位。输出 JSON：
{"action_items": [{"action_id": "a1", "action_type": "task", "title": "...", "owner": "...", "due_date": null, "priority": "medium", "related_entities": [], "dependencies": [], "source_utterance_ids": [], "confidence": 0.85}]}
action_type: task|decision|follow_up|blocker。仅 JSON。"""


async def run_diarize(transcript: str) -> list[dict[str, Any]]:
    mock = _mock_diarize(transcript)
    result = await ainvoke_json(
        DIARIZE_SYSTEM,
        f"转写：\n{transcript[:8000]}",
        mock={"utterances": mock},
    )
    return result.get("utterances", mock)


async def run_extract_todos(
    utterances: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    text = "\n".join(f"[{u.get('speaker')}]{u.get('text')}" for u in utterances)
    mock = _mock_todos(utterances)
    result = await ainvoke_json(
        EXTRACT_SYSTEM,
        f"发言记录：\n{text[:8000]}",
        mock={"todos": mock},
    )
    return result.get("todos", mock)


async def run_structure_actions(
    todos: list[dict[str, Any]],
    utterances: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    mock = _mock_actions(todos, utterances)
    result = await ainvoke_json(
        STRUCTURE_SYSTEM,
        f"待办：{todos}\n发言：{utterances[:20]}",
        mock={"action_items": mock},
    )
    items = result.get("action_items", mock)
    validated: list[dict[str, Any]] = []
    for i, raw in enumerate(items):
        data = dict(raw)
        if not data.get("action_id"):
            data["action_id"] = f"a{i+1}-{uuid.uuid4().hex[:6]}"
        ok, errs = validate_slot_fill(data)
        data["_slot_valid"] = ok
        data["_slot_errors"] = errs
        validated.append(data)
    return validated


def _mock_diarize(transcript: str) -> list[dict[str, Any]]:
    lines = [ln.strip() for ln in transcript.splitlines() if ln.strip()]
    if not lines:
        lines = [transcript[:500]]
    utterances: list[dict[str, Any]] = []
    speaker_pattern = re.compile(r"^([^:：]{1,20})[:：]\s*(.+)$")
    default_speakers = ["主持人", "参会者A", "参会者B"]
    sp_idx = 0
    for i, line in enumerate(lines):
        m = speaker_pattern.match(line)
        if m:
            speaker, text = m.group(1).strip(), m.group(2).strip()
        else:
            speaker = default_speakers[sp_idx % len(default_speakers)]
            text = line
            sp_idx += 1
        utterances.append(
            {
                "id": f"u{i+1}",
                "speaker": speaker,
                "text": text,
                "start_offset": i,
            }
        )
    return utterances


def _mock_todos(utterances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    todo_markers = ("待办", "负责", "下周", "完成", "跟进", "需要", "安排", "提交")
    risk_markers = ("风险", "阻塞")
    todos: list[dict[str, Any]] = []
    covered: set[str] = set()
    tid = 1
    for u in utterances:
        t = u.get("text", "")
        if any(m in t for m in todo_markers):
            todos.append(
                {
                    "id": f"t{tid}",
                    "text": t,
                    "assignee": u.get("speaker"),
                    "deadline": _extract_deadline(t),
                    "utterance_id": u.get("id"),
                }
            )
            covered.add(u.get("id", ""))
            tid += 1
    for u in utterances:
        uid = u.get("id", "")
        if uid in covered:
            continue
        t = u.get("text", "")
        if any(m in t for m in risk_markers):
            todos.append(
                {
                    "id": f"t{tid}",
                    "text": t,
                    "assignee": u.get("speaker"),
                    "deadline": _extract_deadline(t),
                    "utterance_id": uid,
                }
            )
            tid += 1
    if not todos and utterances:
        todos.append(
            {
                "id": "t1",
                "text": utterances[-1].get("text", "会后整理纪要"),
                "assignee": utterances[-1].get("speaker"),
                "deadline": None,
                "utterance_id": utterances[-1].get("id"),
            }
        )
    return todos


def _mock_actions(
    todos: list[dict[str, Any]], utterances: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for i, todo in enumerate(todos):
        text = todo.get("text", "")
        if "阻塞" in text or "风险" in text:
            atype = ActionType.BLOCKER.value
        elif "确认" in text or "结论" in text:
            atype = ActionType.DECISION.value
        else:
            atype = ActionType.TASK.value
        priority = (
            Priority.HIGH.value
            if "紧急" in todo.get("text", "") or "下周" in todo.get("text", "")
            else Priority.MEDIUM.value
        )
        entities = [w for w in ("项目", "系统", "预算", "上线") if w in todo.get("text", "")]
        actions.append(
            {
                "action_id": f"a{i+1}",
                "action_type": atype,
                "title": todo.get("text", "")[:80],
                "owner": todo.get("assignee"),
                "due_date": todo.get("deadline"),
                "priority": priority,
                "related_entities": entities,
                "dependencies": [],
                "source_utterance_ids": [todo.get("utterance_id")]
                if todo.get("utterance_id")
                else [],
                "confidence": 0.82,
            }
        )
    return actions


def _extract_deadline(text: str) -> str | None:
    for pat in (r"下周五", r"下周[一二三四五六日]", r"\d+月\d+日", r"本月底"):
        m = re.search(pat, text)
        if m:
            return m.group()
    return None
