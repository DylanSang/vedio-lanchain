"""平台文案适配 — LLM 根据各平台调性差异化改写标题/描述/标签."""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from config import settings
from models.schemas import Platform
from services.publisher.base import VideoMetadata

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
你是一位精通各短视频平台运营规则的资深文案策划。
请根据以下平台调性改写视频的标题、描述和标签:

- **抖音**: 短标题 + hook手法("看到最后绝了"/"第3个太离谱"), 话题标签如 #热门 #抖音
- **B站**: 信息密度高的标题, 较长描述可带专栏链接, 分区标签, 避免过度标题党
- **小红书**: emoji密集标题 🔥✨, 种草/教程口吻, #话题 密集, 正文像朋友分享
- **快手**: 接地气口语化, 直接描述内容, 少用专业术语
- **微信视频号**: 正式但亲和, 可带公众号引流, 适度正能量

标签要求: 每个平台 5-10 个, 混合热门通用标签和内容专属标签。
"""

_USER_PROMPT = """\
原始标题: {title}
原始描述: {description}
原始标签: {tags}
目标平台: {platform}
视频主题: {topic}

请输出适配后的文案 JSON:
{{
  "title": "适配后标题",
  "description": "适配后描述",
  "tags": ["标签1", "标签2", ...]
}}
"""


def _build_chain() -> Any:
    prompt = ChatPromptTemplate.from_messages([
        ("system", _SYSTEM_PROMPT),
        ("human", _USER_PROMPT),
    ])
    llm = ChatOpenAI(
        model=settings.llm.model,
        api_key=settings.llm.api_key,
        base_url=settings.llm.base_url,
        temperature=0.7,
        max_tokens=800,
    )
    return prompt | llm | JsonOutputParser()


async def adapt_copy_for_platform(
    title: str,
    description: str,
    tags: list[str],
    topic: str,
    platform: Platform,
) -> VideoMetadata:
    """为指定平台适配文案.

    Returns:
        平台专属的 VideoMetadata
    """
    chain = _build_chain()
    result = await chain.ainvoke({
        "title": title,
        "description": description,
        "tags": ", ".join(tags),
        "platform": platform.value,
        "topic": topic,
    })

    adapted = VideoMetadata(
        title=result.get("title", title),
        description=result.get("description", description),
        tags=result.get("tags", tags),
    )
    logger.info("文案适配 [%s]: %s", platform.value, adapted.title[:40])
    return adapted


async def adapt_copy_batch(
    title: str,
    description: str,
    tags: list[str],
    topic: str,
    platforms: list[Platform],
) -> dict[Platform, VideoMetadata]:
    """批量为多个平台适配文案."""
    import asyncio
    tasks = {
        p: asyncio.create_task(adapt_copy_for_platform(title, description, tags, topic, p))
        for p in platforms
    }
    results: dict[Platform, VideoMetadata] = {}
    for p, task in tasks.items():
        try:
            results[p] = await task
        except Exception as e:
            logger.warning("文案适配失败 [%s]: %s, 使用原始文案", p.value, e)
            results[p] = VideoMetadata(title=title, description=description, tags=tags)
    return results
