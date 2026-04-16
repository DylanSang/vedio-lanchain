"""定时发布调度模块单测."""
from __future__ import annotations

from datetime import datetime, time
from unittest.mock import patch, MagicMock

import pytest

from models.schemas import Platform
from services.publish_scheduler import (
    next_golden_time,
    get_publish_schedule,
    schedule_publish,
    _GOLDEN_HOURS,
)


class TestNextGoldenTime:
    def test_returns_future_time(self):
        now = datetime(2026, 3, 31, 10, 0, 0)
        result = next_golden_time(Platform.DOUYIN, after=now)
        assert result > now
        assert result.hour == 12
        assert result.minute == 0

    def test_skips_past_golden_hours(self):
        now = datetime(2026, 3, 31, 13, 0, 0)
        result = next_golden_time(Platform.DOUYIN, after=now)
        assert result.hour == 18

    def test_wraps_to_tomorrow_when_all_passed(self):
        now = datetime(2026, 3, 31, 23, 0, 0)
        result = next_golden_time(Platform.DOUYIN, after=now)
        assert result.day == 1  # April 1
        assert result.month == 4
        assert result.hour == 12

    def test_skips_within_5_minutes(self):
        now = datetime(2026, 3, 31, 11, 54, 0)
        result = next_golden_time(Platform.DOUYIN, after=now)
        assert result.hour == 12

        now = datetime(2026, 3, 31, 11, 57, 0)
        result = next_golden_time(Platform.DOUYIN, after=now)
        assert result.hour == 18

    def test_unknown_platform_default_18h(self):
        now = datetime(2026, 3, 31, 10, 0, 0)
        with patch.dict(_GOLDEN_HOURS, clear=True):
            result = next_golden_time(Platform.DOUYIN, after=now)
        assert result.hour == 18

    def test_all_platforms_have_golden_hours(self):
        for platform in Platform:
            assert platform in _GOLDEN_HOURS


class TestGetPublishSchedule:
    def test_returns_all_platforms(self):
        platforms = [Platform.DOUYIN, Platform.BILIBILI]
        schedule = get_publish_schedule(platforms)
        assert len(schedule) == 2
        assert Platform.DOUYIN in schedule
        assert Platform.BILIBILI in schedule

    def test_all_times_in_future(self):
        platforms = list(Platform)
        schedule = get_publish_schedule(platforms)
        now = datetime.now()
        for platform, scheduled_time in schedule.items():
            assert scheduled_time > now


class TestSchedulePublish:
    def test_adds_job_to_scheduler(self):
        mock_scheduler = MagicMock()
        with patch("services.publish_scheduler.get_scheduler", return_value=mock_scheduler):
            publish_time = schedule_publish(
                platform=Platform.DOUYIN,
                publish_fn=lambda: None,
                job_id="test_job",
            )

            mock_scheduler.add_job.assert_called_once()
            call_kwargs = mock_scheduler.add_job.call_args
            assert call_kwargs.kwargs["id"] == "test_job"
            assert call_kwargs.kwargs["replace_existing"] is True
            assert isinstance(publish_time, datetime)

    def test_passes_kwargs_to_job(self):
        mock_scheduler = MagicMock()
        with patch("services.publish_scheduler.get_scheduler", return_value=mock_scheduler):
            schedule_publish(
                platform=Platform.BILIBILI,
                publish_fn=lambda: None,
                job_id="job_2",
                custom_arg="value",
            )

            call_kwargs = mock_scheduler.add_job.call_args
            assert call_kwargs.kwargs["kwargs"]["custom_arg"] == "value"
