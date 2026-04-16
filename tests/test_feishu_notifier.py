"""飞书通知模块单测."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from models.schemas import (
    ContentPlan,
    ContentVariant,
    EditedVideoResult,
    EditingEvaluation,
    EditingDimension,
    HotspotAnalysis,
    Hotspot,
    Platform,
    PublishResult,
    SceneScript,
    VideoEngine,
    VideoResult,
)


@pytest.fixture(autouse=True)
def mock_lark():
    """Mock lark SDK 避免真实 API 调用."""
    mock_resp = MagicMock()
    mock_resp.success.return_value = True

    mock_client = MagicMock()
    mock_client.im.v1.message.create.return_value = mock_resp

    with patch("services.feishu_notifier._build_client", return_value=mock_client):
        yield mock_client


class TestSendText:
    def test_sends_text_message(self, mock_lark):
        from services.feishu_notifier import send_text

        send_text("chat_123", "测试消息")
        mock_lark.im.v1.message.create.assert_called_once()


class TestSendInteractive:
    def test_sends_card_message(self, mock_lark):
        from services.feishu_notifier import _send_interactive

        _send_interactive("chat_123", {"header": {"title": "test"}})
        mock_lark.im.v1.message.create.assert_called_once()


class TestNotifyAnalyzing:
    def test_sends_analyzing_card(self, mock_lark):
        from services.feishu_notifier import notify_analyzing

        notify_analyzing("chat_1", "AI主题", "wf_001")
        mock_lark.im.v1.message.create.assert_called_once()


class TestNotifyHotspotResult:
    def test_with_hotspot(self, mock_lark):
        from services.feishu_notifier import notify_hotspot_result

        analysis = HotspotAnalysis(
            topic="AI",
            has_hotspot=True,
            overall_score=8,
            hotspots=[Hotspot(angle="科普", description="大众科普", virality_score=8)],
            psychology_insight="好奇心驱动",
            aesthetic_insight="科技美学",
            creativity_insight="新颖角度",
        )
        notify_hotspot_result("chat_1", analysis, "wf_001")
        mock_lark.im.v1.message.create.assert_called_once()

    def test_without_hotspot(self, mock_lark):
        from services.feishu_notifier import notify_hotspot_result

        analysis = HotspotAnalysis(
            topic="普通话题",
            has_hotspot=False,
            overall_score=3,
            summary="该主题缺乏爆发力",
            recommended_topics=["话题A", "话题B"],
        )
        notify_hotspot_result("chat_1", analysis, "wf_001")
        mock_lark.im.v1.message.create.assert_called_once()


class TestNotifyPublishDone:
    def test_mixed_results(self, mock_lark):
        from services.feishu_notifier import notify_publish_done

        results = [
            PublishResult(platform=Platform.DOUYIN, success=True, url="https://douyin.com/1"),
            PublishResult(platform=Platform.BILIBILI, success=False, error="超时"),
        ]
        notify_publish_done("chat_1", results, "AI主题")
        mock_lark.im.v1.message.create.assert_called_once()

    def test_all_success(self, mock_lark):
        from services.feishu_notifier import notify_publish_done

        results = [
            PublishResult(platform=Platform.DOUYIN, success=True, url="https://douyin.com/1"),
        ]
        notify_publish_done("chat_1", results, "主题")
        mock_lark.im.v1.message.create.assert_called_once()


class TestNotifyError:
    def test_sends_error_card(self, mock_lark):
        from services.feishu_notifier import notify_error

        notify_error("chat_1", "wf_001", "连接失败")
        mock_lark.im.v1.message.create.assert_called_once()


class TestNotifyVideosDone:
    def test_sends_videos_card(self, mock_lark):
        from services.feishu_notifier import notify_videos_done

        videos = [
            VideoResult(variant_id=1, perspective="科普", video_path="/v1.mp4", engine=VideoEngine.JIMENG, duration=30),
        ]
        notify_videos_done("chat_1", videos)
        mock_lark.im.v1.message.create.assert_called_once()


class TestNotifyEditingDone:
    def test_with_evaluation(self, mock_lark):
        from services.feishu_notifier import notify_editing_done

        edited = [
            EditedVideoResult(
                variant_id=1,
                perspective="科普",
                original_path="/orig.mp4",
                edited_path="/edited.mp4",
                evaluation=EditingEvaluation(
                    variant_id=1,
                    overall_score=8,
                    dimensions=[EditingDimension(name="流畅度", score=9)],
                    summary="整体优秀",
                ),
            ),
        ]
        notify_editing_done("chat_1", edited)
        mock_lark.im.v1.message.create.assert_called_once()

    def test_without_evaluation(self, mock_lark):
        from services.feishu_notifier import notify_editing_done

        edited = [
            EditedVideoResult(
                variant_id=1, perspective="科普",
                original_path="/o.mp4", edited_path="/e.mp4",
            ),
        ]
        notify_editing_done("chat_1", edited)
        mock_lark.im.v1.message.create.assert_called_once()
