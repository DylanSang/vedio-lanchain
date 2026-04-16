"""资深剪辑师模块 — 从专业角度评估视频并通过 FFmpeg 进行剪辑处理.

评估维度:
1. 各元素比例 — 画面中主体/背景/留白的构图比例
2. 流畅度 — 镜头切换是否自然，节奏是否合理
3. 合理程度 — 画面与主题/旁白是否匹配
4. 创造性 — 是否有新颖的表达手法
5. 审美 — 整体视觉美感
6. 网感 — 是否符合短视频平台的内容调性
7. 镜头语言 — 运镜、景别、角度的运用
8. 色彩处理 — 色调、对比度、饱和度

流程: LLM 分析视频方案 → 生成 FFmpeg 滤镜参数 → 执行后处理
"""
from __future__ import annotations

import asyncio
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from config import settings
from models.schemas import (
    ContentVariant,
    EditedVideoResult,
    EditingDimension,
    EditingEvaluation,
    VideoEngine,
    VideoResult,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
你是一位有20年经验的资深视频剪辑师，精通短视频平台的内容创作规律。

你需要对即将发布的短视频进行专业评估，并给出具体的后期处理方案。

你必须从以下 8 个维度逐一评分(1-10)并给出改进建议:

1. **元素比例** — 画面构图中主体/背景/文字/特效的比例是否合理
2. **流畅度** — 分镜之间的转场是否自然、节奏是否有呼吸感
3. **合理程度** — 画面内容与主题/旁白是否一致、逻辑是否通顺
4. **创造性** — 是否有让人眼前一亮的表达手法、反转或悬念
5. **审美** — 整体视觉美感、画面质感是否高级
6. **网感** — 是否符合目标平台(抖音/B站/小红书等)的调性和热门趋势
7. **镜头语言** — 运镜方式、景别切换、视角运用是否得当
8. **色彩处理** — 色调是否统一、对比度/饱和度是否合适、是否需要调色

然后你需要输出具体的 FFmpeg 后期处理方案(滤镜链)，包括:
- 色彩调整 (亮度/对比度/饱和度/色温)
- 转场效果 (淡入淡出/交叉溶解)
- 速度调节 (某些片段加速/减速)
- 锐化/降噪
- 片头片尾淡入淡出

你的 FFmpeg 滤镜参数必须是可直接执行的合法语法。
"""

_USER_PROMPT = """\
请对以下视频方案进行专业剪辑评估:

**视频标题**: {title}
**视角**: {perspective}
**视频描述**: {description}
**目标平台**: {platforms}

**分镜详情**:
{scenes_detail}

请严格按照以下 JSON 格式输出:
{{
  "variant_id": {variant_id},
  "overall_score": 1-10,
  "dimensions": [
    {{"name": "元素比例", "score": 1-10, "comment": "当前状况", "suggestion": "改进建议"}},
    {{"name": "流畅度", "score": 1-10, "comment": "...", "suggestion": "..."}},
    {{"name": "合理程度", "score": 1-10, "comment": "...", "suggestion": "..."}},
    {{"name": "创造性", "score": 1-10, "comment": "...", "suggestion": "..."}},
    {{"name": "审美", "score": 1-10, "comment": "...", "suggestion": "..."}},
    {{"name": "网感", "score": 1-10, "comment": "...", "suggestion": "..."}},
    {{"name": "镜头语言", "score": 1-10, "comment": "...", "suggestion": "..."}},
    {{"name": "色彩处理", "score": 1-10, "comment": "...", "suggestion": "..."}}
  ],
  "editing_instructions": [
    "具体操作说明1",
    "具体操作说明2"
  ],
  "ffmpeg_filters": "可执行的 FFmpeg 滤镜链参数，如 eq=brightness=0.05:contrast=1.1:saturation=1.2,unsharp=5:5:0.8",
  "summary": "一句话总结剪辑评估和处理方案"
}}
"""


def _build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.llm.model,
        api_key=settings.llm.api_key,
        base_url=settings.llm.base_url,
        temperature=0.5,
        max_tokens=3000,
    )


def _build_chain() -> Any:
    prompt = ChatPromptTemplate.from_messages([
        ("system", _SYSTEM_PROMPT),
        ("human", _USER_PROMPT),
    ])
    llm = _build_llm()
    parser = JsonOutputParser()
    return prompt | llm | parser


def _format_scenes(variant: ContentVariant) -> str:
    """将分镜列表格式化为可读文本."""
    lines: list[str] = []
    for s in variant.scenes:
        lines.append(f"分镜{s.scene_id} ({s.duration}s): {s.prompt}")
        if s.narration:
            lines.append(f"  旁白: {s.narration}")
    return "\n".join(lines)


async def evaluate_video(variant: ContentVariant) -> EditingEvaluation:
    """对单个视频方案进行剪辑师评估.

    Args:
        variant: 内容方案的视角变体

    Returns:
        剪辑评估结果 (含评分和 FFmpeg 滤镜参数)
    """
    chain = _build_chain()

    platforms_str = ", ".join(p.value for p in variant.target_platforms)
    scenes_detail = _format_scenes(variant)

    logger.info("开始剪辑评估: [%s] %s", variant.perspective, variant.title)

    result = await chain.ainvoke({
        "title": variant.title,
        "perspective": variant.perspective,
        "description": variant.description,
        "platforms": platforms_str,
        "scenes_detail": scenes_detail,
        "variant_id": variant.variant_id,
    })

    dimensions = [
        EditingDimension(
            name=d["name"],
            score=d.get("score", 5),
            comment=d.get("comment", ""),
            suggestion=d.get("suggestion", ""),
        )
        for d in result.get("dimensions", [])
    ]

    evaluation = EditingEvaluation(
        variant_id=variant.variant_id,
        overall_score=result.get("overall_score", 5),
        dimensions=dimensions,
        editing_instructions=result.get("editing_instructions", []),
        ffmpeg_filters=result.get("ffmpeg_filters", ""),
        summary=result.get("summary", ""),
    )

    logger.info(
        "剪辑评估完成: [%s] score=%d filters=%s",
        variant.perspective, evaluation.overall_score, evaluation.ffmpeg_filters[:60],
    )
    return evaluation


def _sanitize_filter(raw_filter: str) -> str:
    """确保 FFmpeg 滤镜字符串安全可执行."""
    if not raw_filter or not raw_filter.strip():
        return ""
    safe = re.sub(r"[;&|`$]", "", raw_filter).strip()
    if not safe:
        return ""
    return safe


def apply_ffmpeg_editing(
    input_path: Path,
    output_path: Path,
    evaluation: EditingEvaluation,
) -> Path:
    """根据剪辑评估结果使用 FFmpeg 处理视频.

    始终执行的基础处理:
    - 片头 0.5s 淡入
    - 片尾 0.5s 淡出
    - LLM 给出的自定义滤镜 (色彩/锐化等)
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    filters: list[str] = []

    # LLM 产出的自定义滤镜
    custom = _sanitize_filter(evaluation.ffmpeg_filters)
    if custom:
        filters.append(custom)

    # 淡入淡出
    filters.append("fade=t=in:st=0:d=0.5")
    filters.append("fade=t=out:st=-0.5:d=0.5")

    filter_chain = ",".join(filters) if filters else "null"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vf", filter_chain,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        str(output_path),
    ]

    logger.info("FFmpeg 剪辑处理: %s -> %s", input_path.name, output_path.name)
    logger.debug("FFmpeg 命令: %s", " ".join(cmd))

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.error("FFmpeg 剪辑失败: %s", proc.stderr[:500])
        raise RuntimeError(f"FFmpeg 剪辑处理失败: {proc.stderr[:300]}")

    logger.info("FFmpeg 剪辑完成: %s", output_path)
    return output_path


async def edit_videos_batch(
    videos: list[VideoResult],
    variants: list[ContentVariant],
    max_concurrent: int = 3,
) -> list[EditedVideoResult]:
    """批量评估并剪辑处理所有视频.

    Args:
        videos: 原始视频生成结果
        variants: 对应的内容方案变体 (用于 LLM 评估)
        max_concurrent: 最大并发数

    Returns:
        剪辑后的视频结果列表
    """
    variant_map = {v.variant_id: v for v in variants}
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _edit_one(video: VideoResult) -> EditedVideoResult:
        async with semaphore:
            variant = variant_map.get(video.variant_id)
            if variant is None:
                return EditedVideoResult(
                    variant_id=video.variant_id,
                    perspective=video.perspective,
                    original_path=video.video_path,
                    edited_path=video.video_path,
                    engine=video.engine,
                    duration=video.duration,
                )

            evaluation = await evaluate_video(variant)

            input_path = Path(video.video_path)
            edited_path = input_path.with_name(
                input_path.stem + "_edited" + input_path.suffix
            )

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                apply_ffmpeg_editing,
                input_path,
                edited_path,
                evaluation,
            )

            return EditedVideoResult(
                variant_id=video.variant_id,
                perspective=video.perspective,
                original_path=video.video_path,
                edited_path=str(edited_path),
                evaluation=evaluation,
                engine=video.engine,
                duration=video.duration,
            )

    tasks = [asyncio.create_task(_edit_one(v)) for v in videos]
    results: list[EditedVideoResult] = []
    for video, coro in zip(videos, asyncio.as_completed(tasks)):
        try:
            result = await coro
            results.append(result)
            score = result.evaluation.overall_score if result.evaluation else 0
            logger.info(
                "剪辑完成: [%s] score=%d %s",
                result.perspective, score, result.edited_path,
            )
        except Exception as e:
            logger.error("剪辑处理失败, 使用原始视频: %s", e)
            results.append(EditedVideoResult(
                variant_id=video.variant_id,
                perspective=video.perspective,
                original_path=video.video_path,
                edited_path=video.video_path,
                engine=video.engine,
                duration=video.duration,
            ))

    return results
