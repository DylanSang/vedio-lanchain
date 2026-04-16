"""重试与草稿箱 — 失败任务指数退避重试, 最终失败保存草稿."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TypeVar

from config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def retry_with_backoff(
    fn: Callable[..., Any],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    task_name: str = "",
    **kwargs: Any,
) -> Any:
    """指数退避重试包装器.

    delay 规律: base_delay * 2^attempt (2s, 4s, 8s, ...)
    """
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            if asyncio.iscoroutinefunction(fn):
                return await fn(*args, **kwargs)
            else:
                return fn(*args, **kwargs)
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)
                logger.warning(
                    "[%s] 第 %d 次失败, %.1fs 后重试: %s",
                    task_name, attempt + 1, delay, e,
                )
                await asyncio.sleep(delay)
            else:
                logger.error("[%s] 重试 %d 次后仍然失败: %s", task_name, max_retries, e)

    raise last_error  # type: ignore


def save_to_drafts(
    workflow_id: str,
    variant_id: int,
    platform: str,
    video_path: str,
    metadata: dict,
    error: str,
) -> Path:
    """将发布失败的任务保存到草稿箱, 支持后续手动/自动重试."""
    draft_dir = settings.drafts_dir
    draft_dir.mkdir(parents=True, exist_ok=True)

    draft = {
        "workflow_id": workflow_id,
        "variant_id": variant_id,
        "platform": platform,
        "video_path": video_path,
        "metadata": metadata,
        "error": error,
        "saved_at": datetime.now().isoformat(),
        "retry_count": 0,
        "status": "draft",
    }

    filename = f"{workflow_id}_{variant_id}_{platform}_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    draft_path = draft_dir / filename
    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("已保存到草稿箱: %s", draft_path.name)
    return draft_path


def list_drafts() -> list[dict]:
    """列出所有草稿箱中的待处理任务."""
    draft_dir = settings.drafts_dir
    drafts = []
    for f in sorted(draft_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["draft_file"] = str(f)
            drafts.append(data)
        except Exception as e:
            logger.warning("读取草稿失败: %s: %s", f.name, e)
    return drafts


def mark_draft_completed(draft_path: str) -> None:
    """标记草稿为已完成."""
    p = Path(draft_path)
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        data["status"] = "completed"
        data["completed_at"] = datetime.now().isoformat()
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
