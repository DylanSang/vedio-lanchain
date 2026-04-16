"""品牌标识 — 片头/片尾模板拼接 + 全程水印叠加.

使用 re-encode 模式拼接, 确保不同编码/分辨率/帧率的素材兼容。
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)

_VIDEO_ENCODE_ARGS = ["-c:v", "libx264", "-preset", "fast", "-crf", "23"]
_AUDIO_ENCODE_ARGS = ["-c:a", "aac", "-b:a", "192k"]


def _find_template(kind: str) -> Path | None:
    """在 assets/templates/{kind}/ 下查找第一个视频/图片模板."""
    d = settings.templates_dir / kind
    if not d.exists():
        return None
    for ext in ("*.mp4", "*.mov", "*.png", "*.jpg"):
        files = sorted(d.glob(ext))
        if files:
            return files[0]
    return None


def _get_video_params(video_path: Path) -> tuple[int, int, str]:
    """获取视频的宽、高、帧率."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate",
        "-of", "csv=p=0:s=,",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        parts = result.stdout.strip().split(",")
        return int(parts[0]), int(parts[1]), parts[2]
    except (ValueError, IndexError):
        return 1080, 1920, "30/1"


def prepend_intro(video_path: Path, output_path: Path) -> Path:
    """在视频头部拼接片头模板 (re-encode 确保兼容)."""
    intro = _find_template("intro")
    if intro is None:
        logger.debug("无片头模板, 跳过")
        return video_path

    w, h, fps = _get_video_params(video_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(intro),
        "-i", str(video_path),
        "-filter_complex",
        f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v0];"
        f"[1:v]setsar=1,fps={fps}[v1];"
        f"[v0][0:a][v1][1:a]concat=n=2:v=1:a=1[outv][outa]",
        "-map", "[outv]", "-map", "[outa]",
        *_VIDEO_ENCODE_ARGS, *_AUDIO_ENCODE_ARGS,
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    if proc.returncode != 0:
        logger.warning("片头拼接失败, 尝试无音频模式: %s", proc.stderr[:200])
        return _prepend_intro_no_audio(intro, video_path, output_path, w, h, fps)

    logger.info("片头已拼接: %s", output_path.name)
    return output_path


def _prepend_intro_no_audio(
    intro: Path, video_path: Path, output_path: Path,
    w: int, h: int, fps: str,
) -> Path:
    """片头素材无音轨时的回退方案."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(intro),
        "-i", str(video_path),
        "-filter_complex",
        f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v0];"
        f"[1:v]setsar=1,fps={fps}[v1];"
        f"[v0][v1]concat=n=2:v=1:a=0[outv]",
        "-map", "[outv]", "-map", "1:a?",
        *_VIDEO_ENCODE_ARGS, *_AUDIO_ENCODE_ARGS,
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.warning("片头拼接(无音频)也失败: %s", proc.stderr[:200])
        return video_path
    logger.info("片头已拼接(无音频模式): %s", output_path.name)
    return output_path


def append_outro(video_path: Path, output_path: Path) -> Path:
    """在视频尾部拼接片尾模板 (re-encode 确保兼容)."""
    outro = _find_template("outro")
    if outro is None:
        logger.debug("无片尾模板, 跳过")
        return video_path

    w, h, fps = _get_video_params(video_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(outro),
        "-filter_complex",
        f"[1:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v1];"
        f"[0:v]setsar=1,fps={fps}[v0];"
        f"[v0][0:a][v1][1:a]concat=n=2:v=1:a=1[outv][outa]",
        "-map", "[outv]", "-map", "[outa]",
        *_VIDEO_ENCODE_ARGS, *_AUDIO_ENCODE_ARGS,
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    if proc.returncode != 0:
        logger.warning("片尾拼接失败, 尝试无音频模式: %s", proc.stderr[:200])
        return _append_outro_no_audio(video_path, outro, output_path, w, h, fps)

    logger.info("片尾已拼接: %s", output_path.name)
    return output_path


def _append_outro_no_audio(
    video_path: Path, outro: Path, output_path: Path,
    w: int, h: int, fps: str,
) -> Path:
    """片尾素材无音轨时的回退方案."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(outro),
        "-filter_complex",
        f"[1:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v1];"
        f"[0:v]setsar=1,fps={fps}[v0];"
        f"[v0][v1]concat=n=2:v=1:a=0[outv]",
        "-map", "[outv]", "-map", "0:a?",
        *_VIDEO_ENCODE_ARGS, *_AUDIO_ENCODE_ARGS,
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.warning("片尾拼接(无音频)也失败: %s", proc.stderr[:200])
        return video_path
    logger.info("片尾已拼接(无音频模式): %s", output_path.name)
    return output_path


def overlay_watermark(video_path: Path, output_path: Path) -> Path:
    """在视频上叠加水印 (右上角, 半透明)."""
    wm = _find_template("watermark")
    if wm is None:
        logger.debug("无水印素材, 跳过")
        return video_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(wm),
        "-filter_complex",
        "[1:v]format=rgba,colorchannelmixer=aa=0.3[wm];"
        "[0:v][wm]overlay=W-w-20:20",
        *_VIDEO_ENCODE_ARGS,
        "-c:a", "copy",
        str(output_path),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.warning("水印叠加失败: %s", proc.stderr[:200])
        return video_path

    logger.info("水印已叠加: %s", output_path.name)
    return output_path


def apply_brand_identity(video_path: Path, output_dir: Path, name_prefix: str) -> Path:
    """完整品牌标识流程: 片头 + 水印 + 片尾."""
    current = video_path

    with_intro = output_dir / f"{name_prefix}_intro.mp4"
    current = prepend_intro(current, with_intro)

    with_wm = output_dir / f"{name_prefix}_wm.mp4"
    current = overlay_watermark(current, with_wm)

    with_outro = output_dir / f"{name_prefix}_branded.mp4"
    current = append_outro(current, with_outro)

    return current
