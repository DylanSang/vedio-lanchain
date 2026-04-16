"""视频批量生成模块单测."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from models.schemas import ContentVariant, SceneScript, VideoEngine, VideoResult
from services.video_generator import (
    _safe_name,
    concat_videos,
    generate_videos_batch,
)


class TestSafeName:
    def test_replaces_special_chars(self):
        assert _safe_name('hello/world:test?') == "hello_world_test"

    def test_limits_length(self):
        assert len(_safe_name("a" * 50)) <= 20

    def test_strips_trailing_underscore(self):
        result = _safe_name("hello_")
        assert not result.endswith("_")


class TestConcatVideos:
    def test_single_video_copies(self, tmp_path: Path):
        src = tmp_path / "clip.mp4"
        src.write_text("video data")
        out = tmp_path / "output.mp4"

        result = concat_videos([src], out)
        assert result == out
        assert out.read_text() == "video data"

    def test_multiple_videos_calls_ffmpeg(self, tmp_path: Path):
        clips = []
        for i in range(3):
            p = tmp_path / f"clip_{i}.mp4"
            p.write_text(f"data_{i}")
            clips.append(p)
        out = tmp_path / "output.mp4"

        with patch("services.video_generator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            concat_videos(clips, out)

            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert cmd[0] == "ffmpeg"
            assert "-f" in cmd and "concat" in cmd

    def test_ffmpeg_failure_raises(self, tmp_path: Path):
        clips = [tmp_path / "a.mp4", tmp_path / "b.mp4"]
        for c in clips:
            c.write_text("data")
        out = tmp_path / "output.mp4"

        with patch("services.video_generator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="error!")
            with pytest.raises(RuntimeError, match="FFmpeg 拼接失败"):
                concat_videos(clips, out)


def _make_variant(variant_id: int = 1) -> ContentVariant:
    return ContentVariant(
        variant_id=variant_id,
        perspective="科普讲解",
        title="测试标题",
        description="测试描述",
        scenes=[
            SceneScript(scene_id=1, prompt="A test prompt", duration=5.0, narration="旁白"),
        ],
        tags=["测试"],
    )


class TestGenerateVideosBatch:
    @pytest.mark.asyncio
    async def test_jimeng_engine(self, tmp_path: Path):
        mock_client = AsyncMock()
        mock_client.generate_video_from_prompt.return_value = tmp_path / "scene_01.mp4"
        mock_client.close = AsyncMock()

        with patch("services.video_generator.JimengClient", return_value=mock_client):
            with patch("services.video_generator.settings") as mock_settings:
                mock_settings.videos_dir = tmp_path

                with patch("services.video_generator.concat_videos", return_value=tmp_path / "final.mp4"):
                    results = await generate_videos_batch(
                        [_make_variant(1)], "测试主题", VideoEngine.JIMENG,
                    )

        assert len(results) == 1
        assert results[0].engine == VideoEngine.JIMENG

    @pytest.mark.asyncio
    async def test_xiaoyunque_engine(self, tmp_path: Path):
        mock_bot = AsyncMock()
        mock_bot.generate_video.return_value = tmp_path / "xyq_video.mp4"
        mock_bot.close = AsyncMock()

        with patch("services.video_generator.XiaoyunqueBot", return_value=mock_bot):
            with patch("services.video_generator.settings") as mock_settings:
                mock_settings.videos_dir = tmp_path
                results = await generate_videos_batch(
                    [_make_variant(1)], "测试主题", VideoEngine.XIAOYUNQUE, style="科技风",
                )

        assert len(results) == 1
        assert results[0].engine == VideoEngine.XIAOYUNQUE

    @pytest.mark.asyncio
    async def test_handles_generation_error(self, tmp_path: Path):
        mock_client = AsyncMock()
        mock_client.generate_video_from_prompt.side_effect = RuntimeError("API error")
        mock_client.close = AsyncMock()

        with patch("services.video_generator.JimengClient", return_value=mock_client):
            with patch("services.video_generator.settings") as mock_settings:
                mock_settings.videos_dir = tmp_path
                results = await generate_videos_batch(
                    [_make_variant(1)], "测试主题", VideoEngine.JIMENG,
                )

        assert len(results) == 0
