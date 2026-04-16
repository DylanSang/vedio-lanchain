"""音频处理链 — TTS+BGM 动态 ducking 混音 / 音量归一化 / 与视频合成.

管道: TTS音频段 + BGM → 动态ducking混音 → loudnorm归一化 → 合成到视频
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from services.tts_service import TTSSegment

logger = logging.getLogger(__name__)


def concat_tts_segments(segments: list[TTSSegment], output_path: Path) -> Path | None:
    """将多个 TTS 音频段按顺序拼接为一条完整配音轨."""
    valid = [s for s in segments if s.audio_path and s.audio_path.exists()]
    if not valid:
        return None

    list_file = output_path.with_suffix(".txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for seg in valid:
            f.write(f"file '{seg.audio_path.resolve()}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True)
    list_file.unlink(missing_ok=True)

    if output_path.exists():
        logger.info("TTS 拼接完成: %s", output_path.name)
        return output_path
    return None


def _build_ducking_filter(
    segments: list[TTSSegment],
    bgm_volume_normal: float = 0.6,
    bgm_volume_ducked: float = 0.15,
    fade_duration: float = 0.3,
) -> str:
    """根据 TTS 时间段构建动态 BGM 音量滤镜.

    有旁白时 BGM 降至 bgm_volume_ducked, 无旁白时恢复至 bgm_volume_normal.
    过渡用 fade_duration 秒的渐变避免突变。
    """
    volume_points: list[str] = []
    current_time = 0.0

    for seg in segments:
        if seg.text and seg.duration > 0:
            duck_start = max(0, current_time - fade_duration)
            duck_end = current_time + seg.duration
            restore_end = duck_end + fade_duration

            volume_points.append(f"volume=enable='between(t,{duck_start:.2f},{restore_end:.2f})':"
                                 f"volume={bgm_volume_ducked / bgm_volume_normal:.2f}")
        current_time += seg.target_duration

    if not volume_points:
        return f"volume={bgm_volume_normal}"

    total_dur = sum(s.target_duration for s in segments)
    expr_parts: list[str] = []
    current_time = 0.0

    for seg in segments:
        seg_start = current_time
        seg_end = current_time + seg.target_duration
        if seg.text and seg.duration > 0:
            fade_in_start = max(0, seg_start - fade_duration)
            fade_out_end = min(total_dur, seg_end + fade_duration)
            expr_parts.append(
                f"if(between(t,{seg_start:.2f},{seg_end:.2f}),"
                f"{bgm_volume_ducked},"
                f"if(between(t,{fade_in_start:.2f},{seg_start:.2f}),"
                f"{bgm_volume_normal}-({bgm_volume_normal}-{bgm_volume_ducked})"
                f"*(t-{fade_in_start:.2f})/{fade_duration:.2f},"
                f"if(between(t,{seg_end:.2f},{fade_out_end:.2f}),"
                f"{bgm_volume_ducked}+({bgm_volume_normal}-{bgm_volume_ducked})"
                f"*(t-{seg_end:.2f})/{fade_duration:.2f},"
                f"{bgm_volume_normal})))"
            )
        current_time += seg.target_duration

    if not expr_parts:
        return f"volume={bgm_volume_normal}"

    combined = expr_parts[0]
    for part in expr_parts[1:]:
        combined = f"min({combined},{part})"

    return f"volume='{combined}':eval=frame"


def mix_with_bgm(
    tts_path: Path,
    bgm_path: Path,
    output_path: Path,
    segments: list[TTSSegment] | None = None,
    bgm_volume_normal: float = 0.6,
    bgm_volume_ducked: float = 0.15,
) -> Path:
    """将 TTS 配音与 BGM 混音, BGM 在旁白段自动降低 (动态 ducking)."""
    if segments:
        bgm_filter = _build_ducking_filter(segments, bgm_volume_normal, bgm_volume_ducked)
    else:
        bgm_filter = f"volume={bgm_volume_ducked}"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(tts_path),
        "-i", str(bgm_path),
        "-filter_complex",
        f"[1:a]{bgm_filter},aloop=loop=-1:size=2e+09[bgm];"
        f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[out]",
        "-map", "[out]",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ]

    logger.info("BGM 动态ducking混音: %s + %s -> %s", tts_path.name, bgm_path.name, output_path.name)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.warning("动态ducking失败, 回退静态混音: %s", proc.stderr[:200])
        return _mix_static_fallback(tts_path, bgm_path, output_path, bgm_volume_ducked)

    return output_path


def _mix_static_fallback(
    tts_path: Path, bgm_path: Path, output_path: Path, bgm_volume: float,
) -> Path:
    """静态混音回退: 全程 BGM 低音量."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(tts_path),
        "-i", str(bgm_path),
        "-filter_complex",
        f"[1:a]volume={bgm_volume},aloop=loop=-1:size=2e+09[bgm];"
        f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[out]",
        "-map", "[out]",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.warning("静态混音也失败, 使用纯 TTS: %s", proc.stderr[:200])
        import shutil
        shutil.copy2(tts_path, output_path)
    return output_path


def normalize_audio(input_path: Path, output_path: Path) -> Path:
    """音量归一化 (loudnorm) — 统一到 -16 LUFS (短视频平台标准)."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.warning("音量归一化失败: %s", proc.stderr[:200])
        return input_path
    logger.info("音量归一化完成: %s", output_path.name)
    return output_path


def merge_audio_to_video(video_path: Path, audio_path: Path, output_path: Path) -> Path:
    """将最终混音轨合成到视频中 (替换或添加音轨)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-map", "0:v:0", "-map", "1:a:0",
        "-shortest",
        str(output_path),
    ]
    logger.info("音视频合成: %s + %s -> %s", video_path.name, audio_path.name, output_path.name)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.error("音视频合成失败: %s", proc.stderr[:300])
        raise RuntimeError(f"音视频合成失败: {proc.stderr[:200]}")
    return output_path


async def run_audio_pipeline(
    segments: list[TTSSegment],
    bgm_path: Path | None,
    video_path: Path,
    output_dir: Path,
    name_prefix: str,
) -> Path:
    """完整音频处理管道.

    TTS拼接 -> (可选)BGM动态ducking混音 -> 归一化 -> 合成到视频

    Returns:
        带音频的最终视频路径
    """
    tts_concat = output_dir / f"{name_prefix}_tts_full.mp3"
    tts_track = concat_tts_segments(segments, tts_concat)

    if tts_track is None:
        logger.info("无 TTS 音频, 跳过音频处理")
        return video_path

    if bgm_path and bgm_path.exists():
        mixed = output_dir / f"{name_prefix}_mixed.aac"
        mix_with_bgm(tts_track, bgm_path, mixed, segments=segments)
    else:
        mixed = tts_track

    normalized = output_dir / f"{name_prefix}_norm.aac"
    normalize_audio(mixed, normalized)

    final_video = output_dir / f"{name_prefix}_with_audio.mp4"
    return merge_audio_to_video(video_path, normalized, final_video)
