"""内容方案生成模块单测."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from models.schemas import ContentPlan, FeishuCommand, Platform


def _make_command(topic: str = "AI 发展趋势", variant_count: int = 2) -> FeishuCommand:
    return FeishuCommand(
        topic=topic,
        variant_count=variant_count,
        platforms=[Platform.DOUYIN, Platform.BILIBILI],
    )


_MOCK_LLM_OUTPUT = {
    "topic": "AI 发展趋势",
    "variants": [
        {
            "variant_id": 1,
            "perspective": "科普讲解",
            "title": "3分钟看懂AI发展",
            "description": "科普视角解读AI发展历程",
            "scenes": [
                {
                    "scene_id": 1,
                    "prompt": "A futuristic cityscape with holographic AI interfaces",
                    "duration": 5.0,
                    "narration": "人工智能正在改变我们的世界",
                },
                {
                    "scene_id": 2,
                    "prompt": "Timeline showing AI milestones from 1950 to 2026",
                    "duration": 8.0,
                    "narration": "从图灵测试到ChatGPT",
                },
            ],
            "tags": ["AI", "人工智能", "科技"],
        },
        {
            "variant_id": 2,
            "perspective": "故事叙述",
            "title": "AI的前世今生",
            "description": "用故事讲述AI的发展",
            "scenes": [
                {
                    "scene_id": 1,
                    "prompt": "Alan Turing working at his desk in 1950s style",
                    "duration": 6.0,
                    "narration": "1950年，图灵提出了一个大胆的问题",
                },
            ],
            "tags": ["AI故事", "科技史"],
        },
    ],
}


@pytest.mark.asyncio
async def test_generate_content_plan():
    """测试内容方案生成返回正确结构."""
    with patch("services.content_planner._build_chain") as mock_chain:
        mock_runnable = AsyncMock()
        mock_runnable.ainvoke.return_value = _MOCK_LLM_OUTPUT
        mock_chain.return_value = mock_runnable

        from services.content_planner import generate_content_plan

        cmd = _make_command()
        plan = await generate_content_plan(cmd)

        assert isinstance(plan, ContentPlan)
        assert plan.topic == "AI 发展趋势"
        assert len(plan.variants) == 2
        assert plan.variants[0].perspective == "科普讲解"
        assert len(plan.variants[0].scenes) == 2
        assert plan.variants[0].scenes[0].prompt.startswith("A futuristic")
