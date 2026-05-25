"""Planner Agent：根据转写文本生成多步执行计划。"""

from typing import Any

from app.llm import ainvoke_json


PLANNER_SYSTEM = """你是会议纪要 Planner。输出 JSON：
{
  "steps": [
    {"id": "diarize", "goal": "说话人分离", "priority": 1},
    {"id": "extract_todos", "goal": "待办抽取", "priority": 2},
    {"id": "structure_actions", "goal": "行动项 KG 槽位填充", "priority": 3}
  ],
  "focus_topics": ["主题1"],
  "expected_speakers": 2
}
仅输出 JSON。"""


async def run_planner(transcript: str) -> dict[str, Any]:
    mock = {
        "steps": [
            {"id": "diarize", "goal": "说话人分离与发言分段", "priority": 1},
            {"id": "extract_todos", "goal": "识别待办与承诺", "priority": 2},
            {
                "id": "structure_actions",
                "goal": "行动项结构化并填充知识图谱槽位",
                "priority": 3,
            },
        ],
        "focus_topics": _guess_topics(transcript),
        "expected_speakers": max(2, transcript.count("：") + transcript.count(":")),
    }
    return await ainvoke_json(
        PLANNER_SYSTEM,
        f"会议转写：\n{transcript[:8000]}",
        mock=mock,
    )


def _guess_topics(text: str) -> list[str]:
    keywords = ["项目", "进度", "风险", "预算", "上线", "评审", "需求"]
    return [k for k in keywords if k in text][:5] or ["一般议题"]
