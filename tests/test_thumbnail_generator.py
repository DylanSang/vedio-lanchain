"""测试 thumbnail_generator 模块."""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from models.schemas import Platform
from services import thumbnail_generator


def test_extract_best_frame_calls_ffmpeg(tmp_path: Path) -> None:
    out = tmp_path / "f.jpg"
    vid = tmp_path / "v.mp4"
    with patch("services.thumbnail_generator.subprocess.run") as run:
        out.touch()
        thumbnail_generator.extract_best_frame(vid, out, timestamp=3.0)
    cmd = run.call_args_list[0][0][0]
    assert cmd[0] == "ffmpeg"
    assert "-ss" in cmd and "3.0" in cmd
    assert "-frames:v" in cmd and "1" in cmd


def test_extract_best_frame_retries_with_1s(tmp_path: Path) -> None:
    """首次输出不存在时改用 1.0s 重试."""
    out = tmp_path / "f.jpg"
    vid = tmp_path / "v.mp4"

    def touch_second(*args: object, **kwargs: object) -> MagicMock:
        if "-ss" in args[0] and args[0][args[0].index("-ss") + 1] == "1.0":
            out.touch()
        return MagicMock()

    with patch("services.thumbnail_generator.subprocess.run", side_effect=touch_second) as run:
        thumbnail_generator.extract_best_frame(vid, out, timestamp=3.0)
    assert run.call_count == 2


def test_add_title_text_center_and_stroke(tmp_path: Path) -> None:
    """文字居中、描边与主字."""
    img_path = tmp_path / "in.jpg"
    out_path = tmp_path / "out.jpg"
    mock_img = MagicMock()
    mock_img.width = 400
    mock_img.height = 300
    mock_open = MagicMock()
    mock_open.convert.return_value = mock_img
    mock_draw = MagicMock()
    mock_draw.textbbox.return_value = (0, 0, 200, 100)

    with (
        patch.object(thumbnail_generator.Image, "open", return_value=mock_open),
        patch.object(thumbnail_generator.ImageDraw, "Draw", return_value=mock_draw),
        patch.object(thumbnail_generator, "_find_font", return_value=""),
    ):
        thumbnail_generator.add_title_text(img_path, "标题测试", out_path)

    mock_open.convert.assert_called_once_with("RGBA")
    mock_draw.textbbox.assert_called()
    stroke_calls = [c for c in mock_draw.text.call_args_list if c[1].get("fill") == "black"]
    white_calls = [c for c in mock_draw.text.call_args_list if c[1].get("fill") == "white"]
    assert len(stroke_calls) >= 8
    assert len(white_calls) == 1
    pos_white = white_calls[0][0][0]
    assert pos_white[0] == (400 - 200) // 2
    assert pos_white[1] == 300 // 2 - 100 // 2


@pytest.mark.parametrize(
    "platform,expected_wh",
    [
        (Platform.DOUYIN, (1080, 1920)),
        (Platform.KUAISHOU, (1080, 1920)),
        (Platform.BILIBILI, (1920, 1080)),
        (Platform.XIAOHONGSHU, (1080, 1440)),
        (Platform.WECHAT_VIDEO, (1080, 1920)),
    ],
)
def test_resize_for_platform_dimensions(
    tmp_path: Path,
    platform: Platform,
    expected_wh: tuple[int, int],
) -> None:
    from PIL import Image

    src = tmp_path / "src.jpg"
    dst = tmp_path / "dst.jpg"
    Image.new("RGB", (1080, 1920), color=(1, 2, 3)).save(src)
    thumbnail_generator.resize_for_platform(src, platform, dst)
    with Image.open(dst) as im:
        assert im.size == expected_wh


@pytest.mark.asyncio
async def test_generate_thumbnail_pipeline(tmp_path: Path) -> None:
    """抽帧 -> 标题 -> 平台缩放串联."""
    mock_settings = MagicMock()
    mock_settings.thumbnails_dir = tmp_path

    with (
        patch.object(thumbnail_generator, "settings", mock_settings),
        patch.object(thumbnail_generator, "extract_best_frame", return_value=tmp_path / "f.jpg") as ex,
        patch.object(thumbnail_generator, "add_title_text", return_value=tmp_path / "t.jpg") as ad,
        patch.object(thumbnail_generator, "resize_for_platform", return_value=tmp_path / "final.jpg") as rz,
    ):
        result = await thumbnail_generator.generate_thumbnail(
            Path("/v.mp4"),
            "标题",
            "主题很长很长很长",
            "var1",
            platform=Platform.BILIBILI,
        )

    topic_prefix = "主题很长很长很长"[:10]
    assert result == tmp_path / f"{topic_prefix}_var1_bilibili.jpg"
    ex.assert_called_once()
    assert topic_prefix in str(ex.call_args[0][1])
    ad.assert_called_once()
    rz.assert_called_once()
    assert rz.call_args[0][1] == Platform.BILIBILI
