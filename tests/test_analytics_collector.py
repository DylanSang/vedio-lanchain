"""数据回收与效果分析模块单测."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.analytics_collector import (
    Base,
    VideoAnalytics,
    save_analytics,
    get_variant_comparison,
    get_platform_comparison,
    get_top_topics,
    collect_platform_data,
)
from models.schemas import Platform


@pytest.fixture(autouse=True)
def in_memory_db():
    """为每个测试用例提供干净的内存数据库."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    with patch("services.analytics_collector._SessionLocal", test_session):
        yield test_session


def _make_analytics(
    workflow_id: str = "wf_1",
    variant_id: int = 1,
    platform: str = "douyin",
    period: str = "7d",
    views: int = 1000,
    likes: int = 100,
    comments: int = 20,
    shares: int = 10,
    completion_rate: float = 0.65,
) -> VideoAnalytics:
    return VideoAnalytics(
        workflow_id=workflow_id,
        variant_id=variant_id,
        platform=platform,
        period=period,
        views=views,
        likes=likes,
        comments=comments,
        shares=shares,
        completion_rate=completion_rate,
    )


class TestSaveAnalytics:
    def test_saves_and_persists(self, in_memory_db):
        data = _make_analytics()
        save_analytics(data)

        with in_memory_db() as session:
            rows = session.query(VideoAnalytics).all()
            assert len(rows) == 1
            assert rows[0].workflow_id == "wf_1"
            assert rows[0].views == 1000


class TestGetVariantComparison:
    def test_returns_sorted_by_engagement(self, in_memory_db):
        save_analytics(_make_analytics(variant_id=1, likes=200, comments=50, shares=30, views=1000))
        save_analytics(_make_analytics(variant_id=2, likes=50, comments=10, shares=5, views=1000))

        results = get_variant_comparison("wf_1")
        assert len(results) == 2
        assert results[0]["variant_id"] == 1
        assert results[0]["engagement_rate"] > results[1]["engagement_rate"]

    def test_filters_by_7d_period(self, in_memory_db):
        save_analytics(_make_analytics(period="24h"))
        save_analytics(_make_analytics(period="7d"))

        results = get_variant_comparison("wf_1")
        assert len(results) == 1

    def test_empty_workflow(self, in_memory_db):
        assert get_variant_comparison("nonexistent") == []


class TestGetPlatformComparison:
    def test_returns_correct_platforms(self, in_memory_db):
        save_analytics(_make_analytics(platform="douyin"))
        save_analytics(_make_analytics(platform="bilibili"))

        results = get_platform_comparison("wf_1", 1)
        assert len(results) == 2
        platforms = {r["platform"] for r in results}
        assert platforms == {"douyin", "bilibili"}


class TestGetTopTopics:
    def test_returns_top_n(self, in_memory_db):
        for i in range(5):
            save_analytics(_make_analytics(
                workflow_id=f"wf_{i}", likes=100 * (i + 1),
            ))

        results = get_top_topics(limit=3)
        assert len(results) == 3
        assert results[0]["total_likes"] >= results[1]["total_likes"]


class TestCollectPlatformData:
    @pytest.mark.asyncio
    async def test_creates_analytics_record(self, in_memory_db):
        result = await collect_platform_data(
            platform=Platform.DOUYIN,
            publish_url="https://douyin.com/video/123",
            workflow_id="wf_test",
            variant_id=1,
            period="24h",
        )

        assert result is not None
        assert result.workflow_id == "wf_test"
        assert result.platform == "douyin"

        with in_memory_db() as session:
            assert session.query(VideoAnalytics).count() == 1
