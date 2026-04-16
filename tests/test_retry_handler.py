"""重试与草稿箱模块单测."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest

from services.retry_handler import (
    retry_with_backoff,
    save_to_drafts,
    list_drafts,
    mark_draft_completed,
)


class TestRetryWithBackoff:
    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        fn = AsyncMock(return_value="ok")
        result = await retry_with_backoff(fn, max_retries=3, task_name="test")
        assert result == "ok"
        fn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_success_after_retry(self):
        fn = AsyncMock(side_effect=[ValueError("fail"), ValueError("fail"), "ok"])
        with patch("services.retry_handler.asyncio.sleep", new_callable=AsyncMock):
            result = await retry_with_backoff(fn, max_retries=3, base_delay=0.01, task_name="test")
        assert result == "ok"
        assert fn.await_count == 3

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_raises(self):
        fn = AsyncMock(side_effect=ValueError("always fails"))
        with patch("services.retry_handler.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ValueError, match="always fails"):
                await retry_with_backoff(fn, max_retries=2, base_delay=0.01, task_name="test")
        assert fn.await_count == 3  # initial + 2 retries

    @pytest.mark.asyncio
    async def test_sync_function_supported(self):
        def sync_fn():
            return 42

        result = await retry_with_backoff(sync_fn, max_retries=1, task_name="sync")
        assert result == 42


class TestSaveToDrafts:
    def test_creates_draft_file(self, tmp_path: Path):
        with patch("services.retry_handler.settings") as mock_settings:
            mock_settings.drafts_dir = tmp_path

            path = save_to_drafts(
                workflow_id="wf_001",
                variant_id=1,
                platform="douyin",
                video_path="/path/to/video.mp4",
                metadata={"title": "测试标题", "description": "描述"},
                error="连接超时",
            )

            assert path.exists()
            data = json.loads(path.read_text(encoding="utf-8"))
            assert data["workflow_id"] == "wf_001"
            assert data["platform"] == "douyin"
            assert data["status"] == "draft"
            assert data["error"] == "连接超时"


class TestListDrafts:
    def test_lists_all_drafts(self, tmp_path: Path):
        with patch("services.retry_handler.settings") as mock_settings:
            mock_settings.drafts_dir = tmp_path

            for i in range(3):
                draft = {"workflow_id": f"wf_{i}", "status": "draft"}
                (tmp_path / f"draft_{i}.json").write_text(
                    json.dumps(draft), encoding="utf-8",
                )

            drafts = list_drafts()
            assert len(drafts) == 3

    def test_empty_dir(self, tmp_path: Path):
        with patch("services.retry_handler.settings") as mock_settings:
            mock_settings.drafts_dir = tmp_path
            assert list_drafts() == []


class TestMarkDraftCompleted:
    def test_marks_completed(self, tmp_path: Path):
        draft_file = tmp_path / "draft.json"
        draft_file.write_text(
            json.dumps({"status": "draft", "workflow_id": "wf_1"}),
            encoding="utf-8",
        )

        mark_draft_completed(str(draft_file))
        data = json.loads(draft_file.read_text(encoding="utf-8"))
        assert data["status"] == "completed"
        assert "completed_at" in data

    def test_nonexistent_file_no_error(self):
        mark_draft_completed("/nonexistent/path.json")
