"""测试 bgm_matcher 模块."""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from services import bgm_matcher


def test_list_bgm_files_dir_missing(tmp_path: Path) -> None:
    """目录不存在时返回空列表."""
    mock_settings = MagicMock()
    mock_settings.bgm_dir = tmp_path / "no_such_bgm"
    with patch.object(bgm_matcher, "settings", mock_settings):
        assert bgm_matcher.list_bgm_files("轻松") == []


def test_list_bgm_files_collects_mp3_wav_sorted(tmp_path: Path) -> None:
    """目录存在时收集 .mp3 与 .wav 并排序."""
    cat = tmp_path / "bgm" / "轻松"
    cat.mkdir(parents=True)
    (cat / "b.wav").write_bytes(b"")
    (cat / "a.mp3").write_bytes(b"")
    mock_settings = MagicMock()
    mock_settings.bgm_dir = tmp_path / "bgm"
    with patch.object(bgm_matcher, "settings", mock_settings):
        files = bgm_matcher.list_bgm_files("轻松")
    assert [p.name for p in files] == ["a.mp3", "b.wav"]


@pytest.mark.asyncio
async def test_recommend_bgm_category_success() -> None:
    """LLM 返回 JSON 时原样返回."""
    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(
        return_value={"category": "科技", "reason": "匹配", "energy": "high"},
    )
    with patch.object(bgm_matcher, "_build_chain", return_value=mock_chain):
        out = await bgm_matcher.recommend_bgm_category("t", "d", "p")
    assert out["category"] == "科技"
    assert out["reason"] == "匹配"
    assert out["energy"] == "high"
    mock_chain.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_recommend_bgm_category_fallback_on_error() -> None:
    """链调用失败时回退默认分类."""
    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(side_effect=RuntimeError("api down"))
    with patch.object(bgm_matcher, "_build_chain", return_value=mock_chain):
        out = await bgm_matcher.recommend_bgm_category("t", "d", "p")
    assert out == {"category": "轻松", "reason": "默认", "energy": "medium"}


@pytest.mark.asyncio
async def test_select_bgm_picks_file(tmp_path: Path) -> None:
    """有素材时选中某个文件."""
    cat_dir = tmp_path / "bgm" / "激昂"
    cat_dir.mkdir(parents=True)
    p = cat_dir / "track.mp3"
    p.write_bytes(b"x")
    mock_settings = MagicMock()
    mock_settings.bgm_dir = tmp_path / "bgm"
    mock_rec = AsyncMock(
        return_value={"category": "激昂", "reason": "燃", "energy": "high"},
    )
    with (
        patch.object(bgm_matcher, "settings", mock_settings),
        patch.object(bgm_matcher, "recommend_bgm_category", mock_rec),
        patch.object(bgm_matcher.random, "choice", return_value=p),
    ):
        selected = await bgm_matcher.select_bgm("t", "d", "p")
    assert selected == p


@pytest.mark.asyncio
async def test_select_bgm_fallback_when_recommended_category_empty(tmp_path: Path) -> None:
    """推荐分类下无文件时遍历 _BGM_CATEGORIES 直到找到素材."""
    bgm_root = tmp_path / "bgm"
    file_in_keji = bgm_root / "科技" / "found.mp3"
    file_in_keji.parent.mkdir(parents=True)
    file_in_keji.write_bytes(b"x")
    mock_settings = MagicMock()
    mock_settings.bgm_dir = bgm_root
    mock_rec = AsyncMock(return_value={"category": "激昂", "reason": "无此目录", "energy": "high"})
    with (
        patch.object(bgm_matcher, "settings", mock_settings),
        patch.object(bgm_matcher, "recommend_bgm_category", mock_rec),
        patch.object(bgm_matcher.random, "choice", return_value=file_in_keji),
    ):
        selected = await bgm_matcher.select_bgm("t", "d", "p")
    assert selected == file_in_keji


@pytest.mark.asyncio
async def test_select_bgm_empty_library_returns_none(tmp_path: Path) -> None:
    """素材库全空时返回 None."""
    mock_settings = MagicMock()
    mock_settings.bgm_dir = tmp_path / "bgm"
    (tmp_path / "bgm").mkdir()
    mock_rec = AsyncMock(return_value={"category": "科技", "reason": "x", "energy": "low"})
    with (
        patch.object(bgm_matcher, "settings", mock_settings),
        patch.object(bgm_matcher, "recommend_bgm_category", mock_rec),
        patch.object(bgm_matcher, "list_bgm_files", return_value=[]),
    ):
        assert await bgm_matcher.select_bgm("t", "d", "p") is None
