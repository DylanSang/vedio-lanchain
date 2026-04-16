"""AI 内容方案生成 — 基于 LangChain + LLM，支持同主题多视角变体."""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from config import settings
from models.schemas import ContentPlan, ContentVariant, FeishuCommand, SceneScript

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
你是一位专业的短视频内容策划师。根据用户提供的主题，生成多个不同视角/风格的视频内容方案。

每个方案包含:
- perspective: 视角名称 (如 "科普讲解"、"故事叙述"、"对比评测"、"趣味剪辑"、"情感共鸣" 等)
- title: 适合短视频平台的吸引力标题
- description: 一句话描述视频核心卖点
- scenes: 分镜列表，每个分镜包含:
  - scene_id: 序号
  - prompt: 用于 AI 生图/生视频的英文画面描述 (详细、具体、可直接喂给 Seedance/即梦)
  - duration: 该分镜时长 (秒)，总时长建议 15-60 秒
  - narration: 该分镜的中文旁白/配音文案
- tags: 适合各平台的标签列表 (中文)

要求:
1. 每个方案 4-8 个分镜，总时长 15-60 秒
2. prompt 必须是英文，描述具体画面、构图、光线、风格
3. narration 是中文，用于配音
4. 不同视角之间差异要明显
"""

_USER_PROMPT = """\
主题: {topic}
目标平台: {platforms}
视角数量: {variant_count}
{style_hint}

请严格按照以下 JSON 格式输出，不要输出其他内容:
{{
  "topic": "原始主题",
  "variants": [
    {{
      "variant_id": 1,
      "perspective": "视角名称",
      "title": "视频标题",
      "description": "视频描述",
      "scenes": [
        {{"scene_id": 1, "prompt": "english scene description", "duration": 5.0, "narration": "中文旁白"}}
      ],
      "tags": ["标签1", "标签2"]
    }}
  ]
}}
"""


def _build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.llm.model,
        api_key=settings.llm.api_key,
        base_url=settings.llm.base_url,
        temperature=0.8,
        max_tokens=4096,
    )


def _build_chain() -> Any:
    prompt = ChatPromptTemplate.from_messages([
        ("system", _SYSTEM_PROMPT),
        ("human", _USER_PROMPT),
    ])
    llm = _build_llm()
    parser = JsonOutputParser()
    return prompt | llm | parser


async def generate_content_plan(command: FeishuCommand) -> ContentPlan:
    """根据飞书指令生成内容方案 (含 N 个视角变体)."""
    chain = _build_chain()

    platforms_str = ", ".join(p.value for p in command.platforms)
    style_hint = f"风格偏好: {command.style}" if command.style else ""

    logger.info("开始生成内容方案: topic=%s variants=%d", command.topic, command.variant_count)

    result = await chain.ainvoke({
        "topic": command.topic,
        "platforms": platforms_str,
        "variant_count": command.variant_count,
        "style_hint": style_hint,
    })

    variants: list[ContentVariant] = []
    for v in result.get("variants", []):
        scenes = [
            SceneScript(
                scene_id=s["scene_id"],
                prompt=s["prompt"],
                duration=s.get("duration", 5.0),
                narration=s.get("narration", ""),
            )
            for s in v.get("scenes", [])
        ]
        variant = ContentVariant(
            variant_id=v["variant_id"],
            perspective=v["perspective"],
            title=v["title"],
            description=v.get("description", ""),
            scenes=scenes,
            tags=v.get("tags", []),
            target_platforms=command.platforms,
        )
        variants.append(variant)

    plan = ContentPlan(topic=command.topic, variants=variants)
    logger.info("内容方案生成完成: %d 个视角变体", len(variants))
    return plan
