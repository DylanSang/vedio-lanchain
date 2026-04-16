"""专家+创意师爆点分析 — 从用户心理、审美、创造性等维度分析主题的爆发潜力.

在内容方案生成之前执行:
- 有爆点: 提取爆点关键词，为后续方案生成注入爆点方向
- 无爆点: 推荐 3-5 个相关爆点主题，通过飞书询问用户是否更换
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from config import settings
from models.schemas import Hotspot, HotspotAnalysis

logger = logging.getLogger(__name__)

_HOTSPOT_THRESHOLD = 6

_SYSTEM_PROMPT = """\
你是一个由两位顶尖专家组成的分析团队:

【专家A — 资深内容营销专家】
擅长从用户心理、传播学、平台算法推荐机制的角度分析内容的爆发潜力。
深谙各短视频平台(抖音、B站、小红书、快手、微信视频号)的内容偏好和推荐逻辑。

【专家B — 顶级创意总监】
从审美、创造性、叙事张力、情绪共鸣的角度评估内容能否引发用户停留和互动。
精通视觉冲击力、信息密度、反转/悬念等创意手法在短视频中的运用。

两位专家会对用户提出的主题进行深度联合分析，产出以下内容:

1. **爆点挖掘**: 该主题是否存在可爆发的切入角度
2. **用户心理分析**: 目标受众会因什么心理驱动而点击、看完、互动
3. **审美价值判断**: 该主题在视觉呈现上是否有吸引力
4. **创造性空间**: 该主题是否有足够的创意发挥空间
5. **综合评分**: 1-10 分，6分以上视为有爆点潜力
6. **替代推荐**: 如果评分低于6分，必须推荐 3-5 个相关但更有爆点的替代主题

分析要深入、专业、有数据支撑意识(如"该类内容在抖音的完播率通常在X%")。
"""

_USER_PROMPT = """\
请分析以下短视频主题的爆点潜力:

主题: {topic}
目标平台: {platforms}
风格偏好: {style_hint}

请严格按照以下 JSON 格式输出，不要输出其他内容:
{{
  "topic": "原始主题",
  "has_hotspot": true/false,
  "overall_score": 1-10,
  "hotspots": [
    {{
      "angle": "爆点切入角度",
      "description": "为什么这是爆点",
      "virality_score": 1-10,
      "target_audience": "目标受众描述"
    }}
  ],
  "psychology_insight": "用户心理分析 (为什么会点击/看完/互动)",
  "aesthetic_insight": "审美价值判断 (视觉呈现潜力)",
  "creativity_insight": "创造性空间分析 (创意发挥余地)",
  "recommended_topics": ["替代主题1", "替代主题2", "替代主题3"],
  "summary": "一句话总结分析结论"
}}

注意:
- overall_score >= 6 时 has_hotspot 为 true
- overall_score < 6 时 has_hotspot 为 false，且 recommended_topics 必须包含 3-5 个替代主题
- recommended_topics 中的主题必须比原主题更有爆发潜力，且与原主题相关
"""


def _build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.llm.model,
        api_key=settings.llm.api_key,
        base_url=settings.llm.base_url,
        temperature=0.7,
        max_tokens=3000,
    )


def _build_chain() -> Any:
    prompt = ChatPromptTemplate.from_messages([
        ("system", _SYSTEM_PROMPT),
        ("human", _USER_PROMPT),
    ])
    llm = _build_llm()
    parser = JsonOutputParser()
    return prompt | llm | parser


async def analyze_topic_hotspot(
    topic: str,
    platforms: list[str],
    style: str = "",
) -> HotspotAnalysis:
    """分析主题爆点潜力.

    Args:
        topic: 用户提供的原始主题
        platforms: 目标发布平台列表
        style: 风格偏好

    Returns:
        爆点分析结果，包含评分、爆点列表、推荐替代主题
    """
    chain = _build_chain()

    platforms_str = ", ".join(platforms) if platforms else "全平台"
    style_hint = style or "无特殊偏好"

    logger.info("开始爆点分析: topic=%s", topic)

    result = await chain.ainvoke({
        "topic": topic,
        "platforms": platforms_str,
        "style_hint": style_hint,
    })

    hotspots = [
        Hotspot(
            angle=h["angle"],
            description=h["description"],
            virality_score=h.get("virality_score", 5),
            target_audience=h.get("target_audience", ""),
        )
        for h in result.get("hotspots", [])
    ]

    overall_score = result.get("overall_score", 5)
    has_hotspot = overall_score >= _HOTSPOT_THRESHOLD

    analysis = HotspotAnalysis(
        topic=topic,
        has_hotspot=has_hotspot,
        overall_score=overall_score,
        hotspots=hotspots,
        psychology_insight=result.get("psychology_insight", ""),
        aesthetic_insight=result.get("aesthetic_insight", ""),
        creativity_insight=result.get("creativity_insight", ""),
        recommended_topics=result.get("recommended_topics", []) if not has_hotspot else [],
        summary=result.get("summary", ""),
    )

    logger.info(
        "爆点分析完成: topic=%s score=%d has_hotspot=%s",
        topic, overall_score, has_hotspot,
    )
    return analysis
