"""测试 video_adapter 模块."""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from models.schemas import Platform
from services import video_adapter


def test_get_video_dimensions_from_ffprobe(tmp_path: Path) -> None:
    vid = tmp_path / "a.mp4"
    vid.write_bytes(b"")
    mock_result = MagicMock()
    mock_result.stdout = "1280x720\n"
    with patch("services.video_adapter.subprocess.run", return_value=mock_result) as run:
        w, h = video_adapter._get_video_dimensions(vid)
    assert (w, h) == (1280, 720)
    cmd = run.call_args[0][0]
    assert cmd[0] == "ffprobe"


def test_get_video_dimensions_fallback() -> None:
    mock_result = MagicMock()
    mock_result.stdout = "bad"
    with patch("services.video_adapter.subprocess.run", return_value=mock_result):
        w, h = video_adapter._get_video_dimensions(Path("/x.mp4"))
    assert (w, h) == (1080, 1920)


def test_adapt_video_same_ratio_uses_scale(tmp_path: Path) -> None:
    """源与目标比例接近时用 scale."""
    src = tmp_path / "in.mp4"
    out = tmp_path / "out.mp4"
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    with (
        patch.object(video_adapter, "_get_video_dimensions", return_value=(1080, 1920)),
        patch("services.video_adapter.subprocess.run", return_value=mock_proc) as run,
    ):
        video_adapter.adapt_video_for_platform(src, Platform.DOUYIN, out)
    cmd = run.call_args[0][0]
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert fc.startswith("scale=1080:1920")
    assert "boxblur" not in fc


def test_adapt_video_different_ratio_uses_blur_overlay(tmp_path: Path) -> None:
    """比例不同时用高斯模糊背景 + overlay."""
    src = tmp_path / "in.mp4"
    out = tmp_path / "out.mp4"
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    with (
        patch.object(video_adapter, "_get_video_dimensions", return_value=(1920, 1080)),
        patch("services.video_adapter.subprocess.run", return_value=mock_proc) as run,
    ):
        video_adapter.adapt_video_for_platform(src, Platform.DOUYIN, out)
    cmd = run.call_args[0][0]
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "boxblur=20:20" in fc
    assert "overlay=(W-w)/2:(H-h)/2" in fc


def test_adapt_video_batch_multi_platform(tmp_path: Path) -> None:
    src = tmp_path / "in.mp4"
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    platforms = [Platform.DOUYIN, Platform.BILIBILI, Platform.XIAOHONGSHU]
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    with (
        patch.object(video_adapter, "_get_video_dimensions", return_value=(1080, 1920)),
        patch("services.video_adapter.subprocess.run", return_value=mock_proc),
    ):
        results = video_adapter.adapt_video_batch(src, platforms, out_dir, "clip")
    assert set(results.keys()) == set(platforms)
    for p in platforms:
        assert results[p] == out_dir / f"clip_{p.value}.mp4"


def test_adapt_video_ffmpeg_failure_copies_source(tmp_path: Path) -> None:
    """失败时复制源文件到输出."""
    src = tmp_path / "in.mp4"
    src.write_bytes(b"data")
    out = tmp_path / "out.mp4"
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "ffmpeg error"
    with (
        patch.object(video_adapter, "_get_video_dimensions", return_value=(1080, 1920)),
        patch("services.video_adapter.subprocess.run", return_value=mock_proc),
    ):
        video_adapter.adapt_video_for_platform(src, Platform.DOUYIN, out)
    assert out.read_bytes() == b"data"
