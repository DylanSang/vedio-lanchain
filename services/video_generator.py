"""视频批量生成模块 — 统一接口整合即梦 + 小云雀，支持多视角并行 + FFmpeg 拼接."""
from __future__ import annotations

import asyncio
import logging
import re
import subprocess
from pathlib import Path

from config import settings
from models.schemas import ContentVariant, VideoEngine, VideoResult
from services.jimeng_client import JimengClient
from services.xiaoyunque_bot import XiaoyunqueBot

logger = logging.getLogger(__name__)


def _safe_name(text: str, max_len: int = 20) -> str:
    text = re.sub(r'[\\/:*?"<>|\s]+', "_", text)
    return text[:max_len].strip("_")


# ── FFmpeg 拼接 ──


def concat_videos(video_paths: list[Path], output_path: Path) -> Path:
    """使用 FFmpeg 将多个视频片段拼接为一个完整视频."""
    if len(video_paths) == 1:
        import shutil
        shutil.copy2(video_paths[0], output_path)
        return output_path

    list_file = output_path.with_suffix(".txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for vp in video_paths:
            f.write(f"file '{vp.resolve()}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(output_path),
    ]

    logger.info("FFmpeg 拼接: %d 个片段 -> %s", len(video_paths), output_path)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("FFmpeg 拼接失败: %s", result.stderr)
        raise RuntimeError(f"FFmpeg 拼接失败: {result.stderr}")

    list_file.unlink(missing_ok=True)
    return output_path


# ── 即梦引擎: 分镜逐个生成 + 拼接 ──


async def _generate_with_jimeng(
    variant: ContentVariant,
    topic: str,
    save_dir: Path,
) -> VideoResult:
    """使用即梦 API 按分镜生成视频片段，然后拼接."""
    client = JimengClient()
    try:
        variant_name = _safe_name(variant.perspective)
        variant_dir = save_dir / f"{_safe_name(topic)}_{variant_name}"
        variant_dir.mkdir(parents=True, exist_ok=True)

        scene_videos: list[Path] = []
        for scene in variant.scenes:
            scene_path = await client.generate_video_from_prompt(
                prompt=scene.prompt,
                save_dir=variant_dir,
                filename=f"scene_{scene.scene_id:02d}",
                duration=scene.duration,
            )
            scene_videos.append(scene_path)

        if len(scene_videos) > 1:
            final_path = save_dir / f"{_safe_name(topic)}_{variant_name}_final.mp4"
            concat_videos(scene_videos, final_path)
        else:
            final_path = scene_videos[0]

        total_dur = sum(s.duration for s in variant.scenes)
        return VideoResult(
            variant_id=variant.variant_id,
            perspective=variant.perspective,
            video_path=str(final_path),
            engine=VideoEngine.JIMENG,
            duration=total_dur,
        )
    finally:
        await client.close()


# ── 小云雀引擎: 整体生成 ──


async def _generate_with_xiaoyunque(
    variant: ContentVariant,
    topic: str,
    save_dir: Path,
    style: str = "",
) -> VideoResult:
    """使用小云雀浏览器自动化生成完整视频."""
    bot = XiaoyunqueBot()
    try:
        variant_name = _safe_name(variant.perspective)
        filename = f"{_safe_name(topic)}_{variant_name}"

        narration_text = " ".join(s.narration for s in variant.scenes if s.narration)
        full_topic = f"{variant.title}\n{narration_text}" if narration_text else variant.title

        video_path = await bot.generate_video(
            topic=full_topic,
            style=style,
            save_dir=save_dir,
            filename=filename,
        )

        total_dur = sum(s.duration for s in variant.scenes)
        return VideoResult(
            variant_id=variant.variant_id,
            perspective=variant.perspective,
            video_path=str(video_path),
            engine=VideoEngine.XIAOYUNQUE,
            duration=total_dur,
        )
    finally:
        await bot.close()


# ── 统一入口: 批量并行生成 ──


async def generate_videos_batch(
    variants: list[ContentVariant],
    topic: str,
    engine: VideoEngine = VideoEngine.JIMENG,
    style: str = "",
    max_concurrent: int = 3,
) -> list[VideoResult]:
    """批量并行生成多个视角的视频.

    Args:
        variants: 内容方案的多个视角变体
        topic: 原始主题
        engine: 视频生成引擎
        style: 风格偏好
        max_concurrent: 最大并发数

    Returns:
        视频生成结果列表
    """
    save_dir = settings.videos_dir
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _gen(v: ContentVariant) -> VideoResult:
        async with semaphore:
            logger.info("开始生成视频: [%s] %s", v.perspective, topic)
            if engine == VideoEngine.XIAOYUNQUE:
                return await _generate_with_xiaoyunque(v, topic, save_dir, style)
            return await _generate_with_jimeng(v, topic, save_dir)

    tasks = [asyncio.create_task(_gen(v)) for v in variants]
    results: list[VideoResult] = []
    for coro in asyncio.as_completed(tasks):
        try:
            result = await coro
            results.append(result)
            logger.info("视频完成: [%s] %s", result.perspective, result.video_path)
        except Exception as e:
            logger.error("视频生成失败: %s", e)

    return results
