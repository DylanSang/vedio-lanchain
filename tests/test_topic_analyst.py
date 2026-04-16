"""专家爆点分析模块单测."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from models.schemas import HotspotAnalysis

_MOCK_HAS_HOTSPOT = {
    "topic": "AI发展趋势",
    "has_hotspot": True,
    "overall_score": 8,
    "hotspots": [
        {
            "angle": "AI取代人类工作的焦虑",
            "description": "抓住打工人对AI替代恐惧的普遍心理",
            "virality_score": 9,
            "target_audience": "25-35岁职场白领",
        },
        {
            "angle": "AI创作能力震撼展示",
            "description": "用AI实时生成惊艳作品引发wow感",
            "virality_score": 8,
            "target_audience": "科技爱好者",
        },
    ],
    "psychology_insight": "利用信息差和焦虑感驱动点击",
    "aesthetic_insight": "科技感画面在短视频中具有天然视觉吸引力",
    "creativity_insight": "可做对比实验类内容，创意空间大",
    "recommended_topics": [],
    "summary": "AI话题自带流量，多个爆点角度可切入",
}

_MOCK_NO_HOTSPOT = {
    "topic": "我家猫今天睡觉",
    "has_hotspot": False,
    "overall_score": 3,
    "hotspots": [],
    "psychology_insight": "话题过于日常缺乏共鸣驱动力",
    "aesthetic_insight": "猫咪内容虽有基础但此主题无视觉差异化",
    "creativity_insight": "创意空间极窄",
    "recommended_topics": [
        "猫咪迷惑行为大赏",
        "用AI预测猫咪的梦境",
        "百万粉博主的猫咪拍摄技巧",
    ],
    "summary": "主题缺乏爆发力，建议更换",
}


@pytest.mark.asyncio
async def test_analyze_has_hotspot():
    """测试有爆点的主题分析."""
    with patch("services.topic_analyst._build_chain") as mock_chain:
        mock_runnable = AsyncMock()
        mock_runnable.ainvoke.return_value = _MOCK_HAS_HOTSPOT
        mock_chain.return_value = mock_runnable

        from services.topic_analyst import analyze_topic_hotspot

        result = await analyze_topic_hotspot("AI发展趋势", ["douyin", "bilibili"])

        assert isinstance(result, HotspotAnalysis)
        assert result.has_hotspot is True
        assert result.overall_score == 8
        assert len(result.hotspots) == 2
        assert result.hotspots[0].virality_score == 9
        assert result.recommended_topics == []


@pytest.mark.asyncio
async def test_analyze_no_hotspot():
    """测试无爆点的主题分析，应返回推荐替代主题."""
    with patch("services.topic_analyst._build_chain") as mock_chain:
        mock_runnable = AsyncMock()
        mock_runnable.ainvoke.return_value = _MOCK_NO_HOTSPOT
        mock_chain.return_value = mock_runnable

        from services.topic_analyst import analyze_topic_hotspot

        result = await analyze_topic_hotspot("我家猫今天睡觉", ["xiaohongshu"])

        assert result.has_hotspot is False
        assert result.overall_score == 3
        assert len(result.recommended_topics) >= 3
        assert "猫咪迷惑行为大赏" in result.recommended_topics
