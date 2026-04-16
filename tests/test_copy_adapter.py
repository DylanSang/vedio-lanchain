"""测试 copy_adapter 模块."""
from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

# `services.publisher` 包会导入 playwright；测试环境无该依赖时先占位
if "playwright.async_api" not in sys.modules:
    sys.modules["playwright"] = MagicMock()
    sys.modules["playwright.async_api"] = MagicMock()

import pytest

from models.schemas import Platform
from services.copy_adapter import adapt_copy_batch, adapt_copy_for_platform
from services.publisher.base import VideoMetadata


@pytest.mark.asyncio
async def test_adapt_copy_for_platform_returns_video_metadata() -> None:
    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(
        return_value={
            "title": "抖音标题",
            "description": "描述",
            "tags": ["a", "b"],
        },
    )
    with patch("services.copy_adapter._build_chain", return_value=mock_chain):
        meta = await adapt_copy_for_platform(
            "原题",
            "原述",
            ["t1"],
            "主题",
            Platform.DOUYIN,
        )
    assert isinstance(meta, VideoMetadata)
    assert meta.title == "抖音标题"
    assert meta.description == "描述"
    assert meta.tags == ["a", "b"]
    mock_chain.ainvoke.assert_awaited_once()
    inp = mock_chain.ainvoke.await_args[0][0]
    assert inp["platform"] == Platform.DOUYIN.value
    assert inp["title"] == "原题"


@pytest.mark.asyncio
async def test_adapt_copy_for_platform_partial_llm_fields() -> None:
    """LLM 缺字段时回退到原始值."""
    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(return_value={})
    with patch("services.copy_adapter._build_chain", return_value=mock_chain):
        meta = await adapt_copy_for_platform(
            "原标题",
            "原描述",
            ["x"],
            "topic",
            Platform.KUAISHOU,
        )
    assert meta.title == "原标题"
    assert meta.description == "原描述"
    assert meta.tags == ["x"]


@pytest.mark.asyncio
async def test_adapt_copy_batch_parallel_platform_args() -> None:
    """多平台并行且 platform 参数正确传入."""
    seen_platforms: list[str] = []

    async def fake_invoke(inp: dict) -> dict:
        seen_platforms.append(inp["platform"])
        return {
            "title": f"t-{inp['platform']}",
            "description": "d",
            "tags": [inp["platform"]],
        }

    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(side_effect=fake_invoke)
    with patch("services.copy_adapter._build_chain", return_value=mock_chain):
        plats = [Platform.DOUYIN, Platform.BILIBILI, Platform.XIAOHONGSHU]
        results = await adapt_copy_batch("T", "D", ["g"], "top", plats)
    assert set(seen_platforms) == {p.value for p in plats}
    for p in plats:
        assert p in results
        assert results[p].title == f"t-{p.value}"


@pytest.mark.asyncio
async def test_adapt_copy_batch_fallback_on_exception() -> None:
    """单平台失败时使用原始文案."""
    title, desc, tags = "保留题", "保留述", ["tag1", "tag2"]

    async def ainvoke(inp: dict) -> dict:
        if inp["platform"] == Platform.BILIBILI.value:
            raise RuntimeError("api")
        return {"title": "ok", "description": "d", "tags": ["z"]}

    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(side_effect=ainvoke)
    with patch("services.copy_adapter._build_chain", return_value=mock_chain):
        results = await adapt_copy_batch(
            title,
            desc,
            tags,
            "topic",
            [Platform.DOUYIN, Platform.BILIBILI],
        )
    assert results[Platform.DOUYIN].title == "ok"
    assert results[Platform.BILIBILI].title == title
    assert results[Platform.BILIBILI].description == desc
    assert results[Platform.BILIBILI].tags == tags
