"""BGM 背景音乐匹配 — 根据视频风格/情绪自动选择或生成 BGM.

策略:
1. 本地素材库 assets/bgm/{category}/ 按风格分类检索
2. LLM 根据方案内容推荐情绪标签 → 匹配最接近的 BGM
3. (可选) 调用 AI 音乐生成 API 定制 BGM
"""
from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Any

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from config import settings

logger = logging.getLogger(__name__)

_BGM_CATEGORIES = ["科技", "温馨", "激昂", "悬疑", "轻松"]

_SYSTEM_PROMPT = """\
你是一位专业的短视频音乐总监。根据视频内容描述，推荐最合适的背景音乐风格标签。

可选标签: 科技, 温馨, 激昂, 悬疑, 轻松

请严格输出 JSON: {{"category": "标签", "reason": "选择原因", "energy": "low/medium/high"}}
"""


def _build_chain() -> Any:
    prompt = ChatPromptTemplate.from_messages([
        ("system", _SYSTEM_PROMPT),
        ("human", "视频标题: {title}\n视频描述: {description}\n视角: {perspective}"),
    ])
    llm = ChatOpenAI(
        model=settings.llm.model,
        api_key=settings.llm.api_key,
        base_url=settings.llm.base_url,
        temperature=0.3,
        max_tokens=200,
    )
    return prompt | llm | JsonOutputParser()


def list_bgm_files(category: str) -> list[Path]:
    """列出指定分类下的 BGM 文件."""
    bgm_dir = settings.bgm_dir / category
    if not bgm_dir.exists():
        return []
    return sorted(bgm_dir.glob("*.mp3")) + sorted(bgm_dir.glob("*.wav"))


async def recommend_bgm_category(title: str, description: str, perspective: str) -> dict:
    """LLM 推荐 BGM 风格分类."""
    chain = _build_chain()
    try:
        result = await chain.ainvoke({
            "title": title,
            "description": description,
            "perspective": perspective,
        })
        return result
    except Exception as e:
        logger.warning("BGM 推荐失败, 使用默认: %s", e)
        return {"category": "轻松", "reason": "默认", "energy": "medium"}


async def select_bgm(
    title: str,
    description: str,
    perspective: str,
) -> Path | None:
    """自动选择 BGM 文件.

    Returns:
        BGM 文件路径, 无可用素材时返回 None
    """
    rec = await recommend_bgm_category(title, description, perspective)
    category = rec.get("category", "轻松")

    files = list_bgm_files(category)
    if not files:
        for cat in _BGM_CATEGORIES:
            files = list_bgm_files(cat)
            if files:
                category = cat
                break

    if not files:
        logger.warning("BGM 素材库为空, 跳过 BGM")
        return None

    selected = random.choice(files)
    logger.info("BGM 选择: [%s] %s (原因: %s)", category, selected.name, rec.get("reason", ""))
    return selected
