"""即梦 API 客户端单测."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.jimeng_client import JimengClient


@pytest.mark.asyncio
async def test_sign_produces_authorization():
    """验证签名函数生成 Authorization 头."""
    client = JimengClient()
    headers = {"content-type": "application/json"}
    signed = client._sign("POST", "/", {"Action": "CVProcess"}, headers, b'{}')
    assert "authorization" in signed
    assert signed["authorization"].startswith("HMAC-SHA256")
    await client.close()


@pytest.mark.asyncio
async def test_submit_video_task_returns_task_id():
    """测试提交视频任务返回 task_id."""
    client = JimengClient()
    mock_response = {
        "data": {"task_id": "test_task_123"},
        "ResponseMetadata": {},
    }
    with patch.object(client, "_call_api", new_callable=AsyncMock, return_value=mock_response):
        task_id = await client.submit_video_task("A beautiful sunset over the ocean")
        assert task_id == "test_task_123"
    await client.close()


@pytest.mark.asyncio
async def test_wait_for_video_returns_url_on_done():
    """测试轮询完成时返回视频 URL."""
    client = JimengClient()
    mock_result = {"status": "done", "video_url": "https://example.com/video.mp4"}
    with patch.object(client, "query_video_task", new_callable=AsyncMock, return_value=mock_result):
        url = await client.wait_for_video("task_123")
        assert url == "https://example.com/video.mp4"
    await client.close()
