"""数据回收与效果分析 — 采集各平台播放/互动数据, 支持 A/B 对比.

发布后 24h/48h/7d 定时回收, 数据存入 SQLite, 反哺选题优化。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config import settings
from models.schemas import Platform

logger = logging.getLogger(__name__)

Base = declarative_base()


class VideoAnalytics(Base):
    __tablename__ = "video_analytics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(String, index=True, nullable=False)
    variant_id = Column(Integer, nullable=False)
    platform = Column(String, nullable=False)
    publish_url = Column(String, default="")

    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    favorites = Column(Integer, default=0)
    completion_rate = Column(Float, default=0.0)
    follower_gain = Column(Integer, default=0)

    collected_at = Column(DateTime, default=datetime.utcnow)
    period = Column(String, default="24h")  # "24h" | "48h" | "7d"


_engine = create_engine(f"sqlite:///{settings.output_dir / 'analytics.db'}")
Base.metadata.create_all(_engine)
_SessionLocal = sessionmaker(bind=_engine)


def save_analytics(data: VideoAnalytics) -> None:
    with _SessionLocal() as session:
        session.add(data)
        session.commit()
    logger.info("数据已保存: %s [%s] %s", data.workflow_id, data.platform, data.period)


def get_variant_comparison(workflow_id: str) -> list[dict]:
    """同一工作流不同视角变体的 A/B 效果对比."""
    with _SessionLocal() as session:
        rows = session.query(VideoAnalytics).filter(
            VideoAnalytics.workflow_id == workflow_id,
            VideoAnalytics.period == "7d",
        ).all()

    results = []
    for r in rows:
        results.append({
            "variant_id": r.variant_id,
            "platform": r.platform,
            "views": r.views,
            "likes": r.likes,
            "completion_rate": r.completion_rate,
            "engagement_rate": (r.likes + r.comments + r.shares) / max(r.views, 1),
        })
    return sorted(results, key=lambda x: x["engagement_rate"], reverse=True)


def get_platform_comparison(workflow_id: str, variant_id: int) -> list[dict]:
    """同一变体在不同平台的表现对比."""
    with _SessionLocal() as session:
        rows = session.query(VideoAnalytics).filter(
            VideoAnalytics.workflow_id == workflow_id,
            VideoAnalytics.variant_id == variant_id,
            VideoAnalytics.period == "7d",
        ).all()

    return [
        {
            "platform": r.platform,
            "views": r.views,
            "likes": r.likes,
            "comments": r.comments,
            "shares": r.shares,
            "completion_rate": r.completion_rate,
        }
        for r in rows
    ]


def get_top_topics(limit: int = 10) -> list[dict]:
    """历史表现最佳的主题/工作流 (按总互动量排序)."""
    with _SessionLocal() as session:
        from sqlalchemy import func
        rows = (
            session.query(
                VideoAnalytics.workflow_id,
                func.sum(VideoAnalytics.views).label("total_views"),
                func.sum(VideoAnalytics.likes).label("total_likes"),
                func.avg(VideoAnalytics.completion_rate).label("avg_completion"),
            )
            .filter(VideoAnalytics.period == "7d")
            .group_by(VideoAnalytics.workflow_id)
            .order_by(func.sum(VideoAnalytics.likes).desc())
            .limit(limit)
            .all()
        )
    return [
        {
            "workflow_id": r.workflow_id,
            "total_views": r.total_views,
            "total_likes": r.total_likes,
            "avg_completion": round(r.avg_completion, 2) if r.avg_completion else 0,
        }
        for r in rows
    ]


async def collect_platform_data(
    platform: Platform,
    publish_url: str,
    workflow_id: str,
    variant_id: int,
    period: str = "24h",
) -> Optional[VideoAnalytics]:
    """从平台 API 采集单条视频数据 (桩实现, 需对接各平台 API).

    实际实现需根据平台 API 文档调用:
    - 抖音: 内容数据 API
    - B站: 稿件数据 API
    - 其他: 爬虫或手动录入
    """
    logger.info("数据采集 [%s] %s (%s): %s", platform.value, workflow_id, period, publish_url)

    analytics = VideoAnalytics(
        workflow_id=workflow_id,
        variant_id=variant_id,
        platform=platform.value,
        publish_url=publish_url,
        period=period,
    )

    # TODO: 对接各平台数据 API
    # analytics.views = ...
    # analytics.likes = ...

    save_analytics(analytics)
    return analytics
