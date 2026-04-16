"""多尺寸视频适配 — 同一视频自动裁剪为各平台所需的画面比例.

抖音/快手: 9:16 竖屏 (1080x1920)
B站: 16:9 横屏 (1920x1080)
小红书: 3:4 竖屏 (1080x1440)
微信视频号: 9:16 或 1:1

策略:
- 竖屏→横屏: 上下加高斯模糊背景 + 中间放原画
- 横屏→竖屏: 左右加高斯模糊背景 + 中间放原画
- 相同比例: 直接缩放
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from models.schemas import Platform

logger = logging.getLogger(__name__)

_PLATFORM_SPECS: dict[Platform, tuple[int, int]] = {
    Platform.DOUYIN: (1080, 1920),
    Platform.KUAISHOU: (1080, 1920),
    Platform.BILIBILI: (1920, 1080),
    Platform.XIAOHONGSHU: (1080, 1440),
    Platform.WECHAT_VIDEO: (1080, 1920),
}


def _get_video_dimensions(video_path: Path) -> tuple[int, int]:
    """获取视频宽高."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0:s=x",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        w, h = result.stdout.strip().split("x")
        return int(w), int(h)
    except (ValueError, AttributeError):
        return 1080, 1920


def adapt_video_for_platform(
    video_path: Path,
    platform: Platform,
    output_path: Path,
) -> Path:
    """将视频适配为指定平台的画面尺寸.

    使用高斯模糊背景填充策略保持画面美观。
    """
    target_w, target_h = _PLATFORM_SPECS.get(platform, (1080, 1920))
    src_w, src_h = _get_video_dimensions(video_path)

    src_ratio = src_w / src_h
    target_ratio = target_w / target_h

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if abs(src_ratio - target_ratio) < 0.05:
        vf = f"scale={target_w}:{target_h}"
    else:
        # 高斯模糊背景 + 居中叠加原画
        vf = (
            f"split[bg][fg];"
            f"[bg]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{target_h},boxblur=20:20[blurred];"
            f"[fg]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease[scaled];"
            f"[blurred][scaled]overlay=(W-w)/2:(H-h)/2"
        )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-filter_complex", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "copy",
        str(output_path),
    ]

    logger.info("视频适配 [%s]: %dx%d -> %dx%d", platform.value, src_w, src_h, target_w, target_h)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.error("视频适配失败: %s", proc.stderr[:300])
        import shutil
        shutil.copy2(video_path, output_path)

    return output_path


def adapt_video_batch(
    video_path: Path,
    platforms: list[Platform],
    output_dir: Path,
    name_prefix: str,
) -> dict[Platform, Path]:
    """批量为多个平台适配视频尺寸."""
    results: dict[Platform, Path] = {}
    for platform in platforms:
        output = output_dir / f"{name_prefix}_{platform.value}.mp4"
        results[platform] = adapt_video_for_platform(video_path, platform, output)
    return results
