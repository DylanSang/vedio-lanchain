"""测试 brand_overlay 模块."""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from services import brand_overlay


def test_find_template_missing_dir(tmp_path: Path) -> None:
    mock_settings = MagicMock()
    mock_settings.templates_dir = tmp_path / "templates"
    with patch.object(brand_overlay, "settings", mock_settings):
        assert brand_overlay._find_template("intro") is None


def test_find_template_finds_first_mp4(tmp_path: Path) -> None:
    d = tmp_path / "templates" / "intro"
    d.mkdir(parents=True)
    (d / "z.mp4").write_bytes(b"")
    (d / "a.mp4").write_bytes(b"")
    mock_settings = MagicMock()
    mock_settings.templates_dir = tmp_path / "templates"
    with patch.object(brand_overlay, "settings", mock_settings):
        found = brand_overlay._find_template("intro")
    assert found == d / "a.mp4"


def test_prepend_intro_success(tmp_path: Path) -> None:
    intro = tmp_path / "intro.mp4"
    intro.write_bytes(b"")
    video = tmp_path / "main.mp4"
    out = tmp_path / "out.mp4"
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    with (
        patch.object(brand_overlay, "_find_template", return_value=intro),
        patch.object(brand_overlay, "_get_video_params", return_value=(1080, 1920, "30/1")),
        patch("services.brand_overlay.subprocess.run", return_value=mock_proc) as run,
    ):
        result = brand_overlay.prepend_intro(video, out)
    assert result == out
    cmd = run.call_args[0][0]
    assert "ffmpeg" == cmd[0]
    assert "concat=n=2:v=1:a=1" in cmd[cmd.index("-filter_complex") + 1]


def test_prepend_intro_no_template_returns_input(tmp_path: Path) -> None:
    video = tmp_path / "main.mp4"
    out = tmp_path / "out.mp4"
    with patch.object(brand_overlay, "_find_template", return_value=None):
        assert brand_overlay.prepend_intro(video, out) == video


def test_prepend_intro_fail_then_no_audio_success(tmp_path: Path) -> None:
    """主命令失败时走无音频拼接分支并成功."""
    intro = tmp_path / "intro.mp4"
    intro.write_bytes(b"")
    video = tmp_path / "main.mp4"
    out = tmp_path / "out.mp4"
    fail = MagicMock(returncode=1, stderr="err")
    ok = MagicMock(returncode=0, stderr="")
    with (
        patch.object(brand_overlay, "_find_template", return_value=intro),
        patch.object(brand_overlay, "_get_video_params", return_value=(720, 1280, "25/1")),
        patch("services.brand_overlay.subprocess.run", side_effect=[fail, ok]) as run,
    ):
        result = brand_overlay.prepend_intro(video, out)
    assert result == out
    assert run.call_count == 2
    second_cmd = run.call_args_list[1][0][0]
    assert "concat=n=2:v=1:a=0" in second_cmd[second_cmd.index("-filter_complex") + 1]


def test_append_outro_success(tmp_path: Path) -> None:
    outro = tmp_path / "outro.mov"
    outro.write_bytes(b"")
    video = tmp_path / "main.mp4"
    out = tmp_path / "done.mp4"
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    with (
        patch.object(brand_overlay, "_find_template", return_value=outro),
        patch.object(brand_overlay, "_get_video_params", return_value=(1920, 1080, "24/1")),
        patch("services.brand_overlay.subprocess.run", return_value=mock_proc) as run,
    ):
        result = brand_overlay.append_outro(video, out)
    assert result == out
    cmd = run.call_args[0][0]
    assert "concat=n=2:v=1:a=1" in cmd[cmd.index("-filter_complex") + 1]


def test_append_outro_no_template_returns_input(tmp_path: Path) -> None:
    video = tmp_path / "main.mp4"
    out = tmp_path / "out.mp4"
    with patch.object(brand_overlay, "_find_template", return_value=None):
        assert brand_overlay.append_outro(video, out) == video


def test_overlay_watermark_filter(tmp_path: Path) -> None:
    wm = tmp_path / "wm.png"
    wm.write_bytes(b"")
    video = tmp_path / "v.mp4"
    out = tmp_path / "w.mp4"
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    with (
        patch.object(brand_overlay, "_find_template", return_value=wm),
        patch("services.brand_overlay.subprocess.run", return_value=mock_proc) as run,
    ):
        result = brand_overlay.overlay_watermark(video, out)
    assert result == out
    fc = run.call_args[0][0][run.call_args[0][0].index("-filter_complex") + 1]
    assert "colorchannelmixer=aa=0.3" in fc
    assert "overlay=W-w-20:20" in fc


def test_apply_brand_identity_call_order(tmp_path: Path) -> None:
    """串联顺序: 片头 -> 水印 -> 片尾."""
    video = tmp_path / "in.mp4"
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    paths = [out_dir / "p_intro.mp4", out_dir / "p_wm.mp4", out_dir / "p_branded.mp4"]

    def fake_pre(v: Path, o: Path) -> Path:
        return paths[0]

    def fake_wm(v: Path, o: Path) -> Path:
        return paths[1]

    def fake_out(v: Path, o: Path) -> Path:
        return paths[2]

    with (
        patch.object(brand_overlay, "prepend_intro", side_effect=fake_pre) as m_pre,
        patch.object(brand_overlay, "overlay_watermark", side_effect=fake_wm) as m_wm,
        patch.object(brand_overlay, "append_outro", side_effect=fake_out) as m_out,
    ):
        final = brand_overlay.apply_brand_identity(video, out_dir, "clip")

    assert final == paths[2]
    assert m_pre.call_args == call(video, out_dir / "clip_intro.mp4")
    assert m_wm.call_args == call(paths[0], out_dir / "clip_wm.mp4")
    assert m_out.call_args == call(paths[1], out_dir / "clip_branded.mp4")
