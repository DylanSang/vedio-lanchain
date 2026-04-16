"""方案导出 — 将 ContentPlan 保存为可读的 Markdown 文件."""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

from config import settings
from models.schemas import ContentPlan, ContentVariant

logger = logging.getLogger(__name__)


def _safe_filename(text: str, max_len: int = 30) -> str:
    """将中文/特殊字符处理为安全文件名."""
    text = re.sub(r'[\\/:*?"<>|\s]+', "_", text)
    return text[:max_len].strip("_")


def _render_variant_md(variant: ContentVariant, topic: str) -> str:
    """将单个视角变体渲染为 Markdown 字符串."""
    lines: list[str] = []
    lines.append(f"# {variant.title}")
    lines.append("")
    lines.append(f"**主题**: {topic}")
    lines.append(f"**视角**: {variant.perspective}")
    lines.append(f"**描述**: {variant.description}")
    lines.append(f"**标签**: {', '.join(variant.tags)}")
    platforms = ", ".join(p.value for p in variant.target_platforms)
    lines.append(f"**目标平台**: {platforms}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 分镜脚本")
    lines.append("")

    total_duration = 0.0
    for scene in variant.scenes:
        total_duration += scene.duration
        lines.append(f"### 分镜 {scene.scene_id} ({scene.duration}s)")
        lines.append("")
        lines.append(f"**画面 Prompt (EN)**:")
        lines.append(f"> {scene.prompt}")
        lines.append("")
        if scene.narration:
            lines.append(f"**旁白文案**:")
            lines.append(f"> {scene.narration}")
            lines.append("")

    lines.append("---")
    lines.append(f"**总时长**: {total_duration:.1f}s")
    lines.append("")
    return "\n".join(lines)


def export_plan(plan: ContentPlan) -> list[Path]:
    """将内容方案导出为 Markdown 文件，每个视角变体一个文件.

    Returns:
        生成的文件路径列表.
    """
    output_dir = settings.plans_dir
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    topic_safe = _safe_filename(plan.topic)

    exported: list[Path] = []
    for variant in plan.variants:
        perspective_safe = _safe_filename(variant.perspective, max_len=15)
        filename = f"{topic_safe}_{perspective_safe}_{timestamp}.md"
        filepath = output_dir / filename

        md_content = _render_variant_md(variant, plan.topic)
        filepath.write_text(md_content, encoding="utf-8")

        logger.info("方案已导出: %s", filepath)
        exported.append(filepath)

    return exported
