"""测试 subtitle_generator 模块."""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from models.schemas import Platform
from services.subtitle_generator import (
    _format_ass_time,
    _format_srt_time,
    burn_subtitles,
    generate_ass,
    generate_srt,
)
from services.tts_service import TTSSegment


def _seg(
    text: str,
    duration: float = 1.0,
    target_duration: float = 2.0,
    scene_id: int = 0,
) -> TTSSegment:
    return TTSSegment(
        scene_id=scene_id,
        text=text,
        audio_path=Path("/tmp/x.wav"),
        duration=duration,
        target_duration=target_duration,
    )


def test_format_srt_time_boundaries() -> None:
    assert _format_srt_time(0.0) == "00:00:00,000"
    assert _format_srt_time(3661.5) == "01:01:01,500"
    assert _format_srt_time(59.999)[:8] == "00:00:59"


def test_format_ass_time_boundaries() -> None:
    assert _format_ass_time(0.0) == "0:00:00.00"
    assert _format_ass_time(3661.25) == "1:01:01.25"


def test_generate_srt_format_and_indices(tmp_path: Path) -> None:
    """序号、时间轴与空文本跳过."""
    segments = [
        _seg("第一句", duration=1.0, target_duration=2.0),
        _seg("", duration=0.0, target_duration=1.0),
        _seg("第二句", duration=1.5, target_duration=2.0),
    ]
    out = tmp_path / "out.srt"
    generate_srt(segments, out)
    written = out.read_text(encoding="utf-8")
    assert "1\n" in written
    assert "00:00:00,000 --> 00:00:01,000" in written
    assert "第一句" in written
    assert "2\n" in written
    assert "00:00:03,000 --> 00:00:04,500" in written
    assert "第二句" in written


def test_generate_ass_header_and_dialogue(tmp_path: Path) -> None:
    """ASS 头与 Dialogue 行."""
    segments = [_seg("你好", duration=2.0, target_duration=3.0)]
    out = tmp_path / "out.ass"
    with patch.object(Path, "write_text") as mock_write:
        generate_ass(segments, out, platform=Platform.BILIBILI)
    content = mock_write.call_args[0][0]
    assert "[Script Info]" in content
    assert "[V4+ Styles]" in content
    assert "PlayResX: 1080" in content
    assert "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,你好" in content


@pytest.mark.parametrize(
    "platform,expect_substr",
    [
        (Platform.BILIBILI, "Arial,28"),
        (Platform.XIAOHONGSHU, "PingFang SC,32"),
        (Platform.DOUYIN, "Arial,36"),
    ],
)
def test_generate_ass_platform_styles(
    tmp_path: Path,
    platform: Platform,
    expect_substr: str,
) -> None:
    segments = [_seg("x", duration=1.0, target_duration=1.0)]
    out = tmp_path / "p.ass"
    with patch.object(Path, "write_text") as mock_write:
        generate_ass(segments, out, platform=platform)
    assert expect_substr in mock_write.call_args[0][0]


def test_burn_subtitles_ass_filter(tmp_path: Path) -> None:
    """ASS 使用 ass 滤镜."""
    v, s, o = tmp_path / "v.mp4", tmp_path / "c.ass", tmp_path / "o.mp4"
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    with patch("services.subtitle_generator.subprocess.run", return_value=mock_proc) as run:
        burn_subtitles(v, s, o)
    cmd = run.call_args[0][0]
    assert "-vf" in cmd
    vf_idx = cmd.index("-vf") + 1
    assert "ass=" in cmd[vf_idx]


def test_burn_subtitles_srt_filter(tmp_path: Path) -> None:
    """SRT 使用 subtitles 滤镜."""
    v, s, o = tmp_path / "v.mp4", tmp_path / "c.srt", tmp_path / "o.mp4"
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    with patch("services.subtitle_generator.subprocess.run", return_value=mock_proc) as run:
        burn_subtitles(v, s, o)
    cmd = run.call_args[0][0]
    vf_idx = cmd.index("-vf") + 1
    assert "subtitles=" in cmd[vf_idx]
    assert "ffmpeg" == cmd[0]
    assert "-c:v" in cmd and "libx264" in cmd
    assert "-c:a" in cmd and "copy" in cmd
