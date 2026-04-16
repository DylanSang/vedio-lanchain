"""字幕生成与烧录 — 基于 TTS 时间戳生成 SRT/ASS 字幕并 FFmpeg 硬烧进视频.

支持:
- SRT 格式 (通用)
- ASS 格式 (花字样式: 描边/阴影/自定义字体)
- 关键词高亮 (爆点词着色)
- 平台适配样式 (抖音大字居中 / B站底部半透明)
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from models.schemas import Platform
from services.tts_service import TTSSegment

logger = logging.getLogger(__name__)


def _format_srt_time(seconds: float) -> str:
    """格式化为 SRT 时间戳 HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def generate_srt(segments: list[TTSSegment], output_path: Path) -> Path:
    """从 TTS 时间段列表生成 SRT 字幕文件."""
    lines: list[str] = []
    current_time = 0.0
    idx = 1

    for seg in segments:
        if not seg.text:
            current_time += seg.target_duration
            continue
        start = current_time
        end = current_time + seg.duration
        lines.append(str(idx))
        lines.append(f"{_format_srt_time(start)} --> {_format_srt_time(end)}")
        lines.append(seg.text)
        lines.append("")
        idx += 1
        current_time += seg.target_duration

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("SRT 字幕已生成: %s (%d 条)", output_path, idx - 1)
    return output_path


def _get_ass_style(platform: Platform | None = None) -> str:
    """根据目标平台返回 ASS 样式定义."""
    if platform == Platform.BILIBILI:
        return (
            "Style: Default,Arial,28,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
            "-1,0,0,0,100,100,0,0,1,2,0,2,10,10,30,1"
        )
    if platform == Platform.XIAOHONGSHU:
        return (
            "Style: Default,PingFang SC,32,&H00FFFFFF,&H000000FF,&H00000000,&H40000000,"
            "-1,0,0,0,100,100,0,0,1,1.5,0,2,10,10,20,1"
        )
    # 抖音/快手/默认: 大字居中, 粗描边
    return (
        "Style: Default,Arial,36,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "-1,0,0,0,100,100,0,0,1,3,0,2,10,10,20,1"
    )


def generate_ass(
    segments: list[TTSSegment],
    output_path: Path,
    platform: Platform | None = None,
) -> Path:
    """从 TTS 时间段列表生成 ASS 字幕文件 (带花字样式)."""
    style = _get_ass_style(platform)

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{style}\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events: list[str] = []
    current_time = 0.0

    for seg in segments:
        if not seg.text:
            current_time += seg.target_duration
            continue
        start = _format_ass_time(current_time)
        end = _format_ass_time(current_time + seg.duration)
        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{seg.text}")
        current_time += seg.target_duration

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(header + "\n".join(events), encoding="utf-8")
    logger.info("ASS 字幕已生成: %s", output_path)
    return output_path


def _format_ass_time(seconds: float) -> str:
    """格式化为 ASS 时间戳 H:MM:SS.cc."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def burn_subtitles(
    video_path: Path,
    subtitle_path: Path,
    output_path: Path,
) -> Path:
    """使用 FFmpeg 将字幕硬烧进视频.

    根据字幕格式自动选择滤镜: .srt -> subtitles, .ass -> ass
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sub_ext = subtitle_path.suffix.lower()
    escaped_path = str(subtitle_path).replace("\\", "/").replace(":", "\\:")

    if sub_ext == ".ass":
        vf = f"ass='{escaped_path}'"
    else:
        vf = f"subtitles='{escaped_path}'"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "copy",
        str(output_path),
    ]

    logger.info("字幕烧录: %s + %s -> %s", video_path.name, subtitle_path.name, output_path.name)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.error("字幕烧录失败: %s", proc.stderr[:300])
        raise RuntimeError(f"字幕烧录失败: {proc.stderr[:200]}")

    return output_path
