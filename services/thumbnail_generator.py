"""封面图生成 — AI 生图 / 智能抽帧 + 标题文字合成, 多平台尺寸适配."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import settings
from models.schemas import Platform

logger = logging.getLogger(__name__)

_PLATFORM_SIZES: dict[Platform, tuple[int, int]] = {
    Platform.DOUYIN: (1080, 1920),
    Platform.KUAISHOU: (1080, 1920),
    Platform.BILIBILI: (1920, 1080),
    Platform.XIAOHONGSHU: (1080, 1440),
    Platform.WECHAT_VIDEO: (1080, 1920),
}


def extract_best_frame(video_path: Path, output_path: Path, timestamp: float = 3.0) -> Path:
    """从视频中抽取指定时间点的帧作为封面候选."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(timestamp),
        "-i", str(video_path),
        "-frames:v", "1",
        "-q:v", "2",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True)
    if not output_path.exists():
        cmd[3] = "1.0"
        subprocess.run(cmd, capture_output=True, text=True)
    logger.info("抽帧完成: %s @ %.1fs", output_path.name, timestamp)
    return output_path


def _find_font() -> str:
    """查找可用的中文字体."""
    candidates = [
        settings.fonts_dir / "PingFang.ttf",
        settings.fonts_dir / "NotoSansSC-Bold.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    for c in candidates:
        p = Path(c) if isinstance(c, str) else c
        if p.exists():
            return str(p)
    return ""


def add_title_text(
    image_path: Path,
    title: str,
    output_path: Path,
    font_size: int = 72,
) -> Path:
    """在图片上叠加标题文字 (带描边效果)."""
    img = Image.open(image_path).convert("RGBA")
    draw = ImageDraw.Draw(img)

    font_path = _find_font()
    if font_path:
        font = ImageFont.truetype(font_path, font_size)
    else:
        font = ImageFont.load_default()

    max_chars_per_line = img.width // (font_size // 2 + 2)
    lines: list[str] = []
    for i in range(0, len(title), max_chars_per_line):
        lines.append(title[i:i + max_chars_per_line])
    text = "\n".join(lines)

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (img.width - tw) // 2
    y = img.height // 2 - th // 2

    # 描边
    for dx, dy in [(-2, -2), (-2, 2), (2, -2), (2, 2), (-3, 0), (3, 0), (0, -3), (0, 3)]:
        draw.text((x + dx, y + dy), text, fill="black", font=font)
    draw.text((x, y), text, fill="white", font=font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), quality=95)
    logger.info("封面文字合成: %s", output_path.name)
    return output_path


def resize_for_platform(image_path: Path, platform: Platform, output_path: Path) -> Path:
    """调整封面图尺寸以适配指定平台."""
    w, h = _PLATFORM_SIZES.get(platform, (1080, 1920))
    img = Image.open(image_path).convert("RGB")

    src_ratio = img.width / img.height
    dst_ratio = w / h

    if src_ratio > dst_ratio:
        new_h = h
        new_w = int(h * src_ratio)
    else:
        new_w = w
        new_h = int(w / src_ratio)

    img = img.resize((new_w, new_h), Image.LANCZOS)

    left = (new_w - w) // 2
    top = (new_h - h) // 2
    img = img.crop((left, top, left + w, top + h))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), quality=95)
    logger.info("封面尺寸适配: %s -> %dx%d", output_path.name, w, h)
    return output_path


async def generate_thumbnail(
    video_path: Path,
    title: str,
    topic: str,
    variant_name: str,
    platform: Platform = Platform.DOUYIN,
) -> Path:
    """完整流程: 抽帧 -> 文字合成 -> 平台尺寸适配.

    Returns:
        最终封面图路径
    """
    save_dir = settings.thumbnails_dir
    base_name = f"{topic[:10]}_{variant_name}"

    frame_path = save_dir / f"{base_name}_frame.jpg"
    extract_best_frame(video_path, frame_path)

    titled_path = save_dir / f"{base_name}_titled.jpg"
    add_title_text(frame_path, title, titled_path)

    final_path = save_dir / f"{base_name}_{platform.value}.jpg"
    resize_for_platform(titled_path, platform, final_path)

    return final_path
