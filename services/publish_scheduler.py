"""定时发布调度 — 根据各平台黄金时间安排视频发布.

各平台流量高峰经验值:
- 抖音: 12:00, 18:00-20:00
- B站: 17:00-19:00
- 小红书: 20:00-22:00
- 快手: 19:00-21:00
- 微信视频号: 20:00-22:00
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from typing import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from models.schemas import Platform

logger = logging.getLogger(__name__)

_GOLDEN_HOURS: dict[Platform, list[time]] = {
    Platform.DOUYIN: [time(12, 0), time(18, 0), time(20, 0)],
    Platform.BILIBILI: [time(17, 0), time(18, 30)],
    Platform.XIAOHONGSHU: [time(20, 0), time(21, 30)],
    Platform.KUAISHOU: [time(19, 0), time(20, 30)],
    Platform.WECHAT_VIDEO: [time(20, 0), time(21, 0)],
}

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
        _scheduler.start()
    return _scheduler


def next_golden_time(platform: Platform, after: datetime | None = None) -> datetime:
    """计算指定平台的下一个黄金发布时间."""
    now = after or datetime.now()
    hours = _GOLDEN_HOURS.get(platform, [time(18, 0)])

    for golden in sorted(hours):
        candidate = now.replace(hour=golden.hour, minute=golden.minute, second=0, microsecond=0)
        if candidate > now + timedelta(minutes=5):
            return candidate

    # 所有今天的黄金时间都已过, 取明天第一个
    tomorrow = now + timedelta(days=1)
    first = sorted(hours)[0]
    return tomorrow.replace(hour=first.hour, minute=first.minute, second=0, microsecond=0)


def schedule_publish(
    platform: Platform,
    publish_fn: Callable,
    job_id: str,
    **kwargs,
) -> datetime:
    """将发布任务加入定时调度队列.

    Returns:
        计划的发布时间
    """
    publish_time = next_golden_time(platform)
    scheduler = get_scheduler()

    scheduler.add_job(
        publish_fn,
        trigger=DateTrigger(run_date=publish_time),
        id=job_id,
        kwargs=kwargs,
        replace_existing=True,
    )

    logger.info("定时发布已调度: [%s] %s -> %s", platform.value, job_id, publish_time.isoformat())
    return publish_time


def get_publish_schedule(platforms: list[Platform]) -> dict[Platform, datetime]:
    """预览各平台的计划发布时间 (不实际调度)."""
    return {p: next_golden_time(p) for p in platforms}
