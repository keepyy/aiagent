"""统一 LLM 调用：有 Key 走 OpenAI，否则 Mock。"""

import json
import re
from typing import Any

from app.config import settings


def _get_chat_model():
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.2,
    )


async def ainvoke_json(system: str, user: str, mock: dict[str, Any] | None = None) -> dict[str, Any]:
    if settings.effective_mock:
        return mock or {"raw": user[:200]}
    from langchain_core.messages import HumanMessage, SystemMessage

    model = _get_chat_model()
    resp = await model.ainvoke(
        [SystemMessage(content=system), HumanMessage(content=user)]
    )
    text = resp.content if isinstance(resp.content, str) else str(resp.content)
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return json.loads(match.group())
    return {"text": text}
