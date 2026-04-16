"""TTS 配音服务 — 将分镜旁白文案转为语音音频.

支持引擎:
- edge-tts (免费, 微软 Edge 语音合成, 多音色)
- volcengine (火山引擎 TTS, 高质量, 需 API Key)

输出: 每个分镜一个 wav 文件 + 带时间戳的音频段列表
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class TTSSegment:
    """单条 TTS 音频段."""
    scene_id: int
    text: str
    audio_path: Path
    duration: float  # 实际音频时长 (秒)
    target_duration: float  # 分镜目标时长 (秒)


def _safe_name(text: str, max_len: int = 20) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", text)[:max_len].strip("_")


async def _generate_edge_tts(text: str, output_path: Path, voice: str) -> float:
    """使用 edge-tts 生成语音."""
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output_path))

    return _get_audio_duration(output_path)


async def _generate_tts(text: str, output_path: Path, voice: str) -> float:
    """根据配置的 TTS_ENGINE 选择引擎生成语音."""
    engine = settings.tts.engine.lower()
    if engine == "edge-tts":
        return await _generate_edge_tts(text, output_path, voice)
    else:
        logger.warning("未支持的 TTS 引擎 '%s', 回退到 edge-tts", engine)
        return await _generate_edge_tts(text, output_path, voice)


def _get_audio_duration(path: Path) -> float:
    """获取音频文件时长 (秒)."""
    import subprocess
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


def _adjust_duration(audio_path: Path, target_duration: float, actual_duration: float) -> Path:
    """调整音频时长以匹配分镜目标时长 — 过长截断, 过短尾部补静音."""
    import subprocess

    if abs(actual_duration - target_duration) < 0.3:
        return audio_path

    adjusted_path = audio_path.with_name(audio_path.stem + "_adj" + audio_path.suffix)

    if actual_duration > target_duration:
        cmd = [
            "ffmpeg", "-y", "-i", str(audio_path),
            "-t", str(target_duration),
            "-c", "copy", str(adjusted_path),
        ]
    else:
        pad_duration = target_duration - actual_duration
        cmd = [
            "ffmpeg", "-y", "-i", str(audio_path),
            "-af", f"apad=pad_dur={pad_duration}",
            "-t", str(target_duration),
            str(adjusted_path),
        ]

    subprocess.run(cmd, capture_output=True, text=True)
    return adjusted_path if adjusted_path.exists() else audio_path


async def generate_tts_for_scenes(
    scenes: list[dict],
    topic: str,
    variant_name: str,
) -> list[TTSSegment]:
    """为一组分镜生成 TTS 配音.

    Args:
        scenes: [{"scene_id": int, "narration": str, "duration": float}, ...]
        topic: 视频主题 (用于文件命名)
        variant_name: 视角名称

    Returns:
        TTS 音频段列表
    """
    voice = settings.tts.voice
    save_dir = settings.audio_dir / f"{_safe_name(topic)}_{_safe_name(variant_name)}"
    save_dir.mkdir(parents=True, exist_ok=True)

    segments: list[TTSSegment] = []
    for scene in scenes:
        scene_id = scene["scene_id"]
        narration = scene.get("narration", "").strip()
        target_dur = scene.get("duration", 5.0)

        if not narration:
            segments.append(TTSSegment(
                scene_id=scene_id, text="",
                audio_path=Path(""), duration=0.0,
                target_duration=target_dur,
            ))
            continue

        output_path = save_dir / f"tts_scene_{scene_id:02d}.mp3"
        logger.info("TTS 生成: scene_%02d [%s] %s...", scene_id, voice, narration[:30])

        actual_dur = await _generate_tts(narration, output_path, voice)

        final_path = _adjust_duration(output_path, target_dur, actual_dur)
        final_dur = _get_audio_duration(final_path) if final_path != output_path else actual_dur

        segments.append(TTSSegment(
            scene_id=scene_id,
            text=narration,
            audio_path=final_path,
            duration=final_dur,
            target_duration=target_dur,
        ))

    logger.info("TTS 生成完成: %d 个分镜, 保存到 %s", len(segments), save_dir)
    return segments
