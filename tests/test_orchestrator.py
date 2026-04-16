"""Orchestrator 工作流编排单测 + 消息解析测试."""
from __future__ import annotations

import pytest

from bot import parse_command, parse_confirmation, UserConfirmation
from models.schemas import FeishuCommand, Platform, VideoEngine


class TestParseCommand:
    """测试飞书消息解析."""

    def test_basic_command(self):
        text = "#视频 AI发展趋势"
        cmd = parse_command(text)
        assert cmd is not None
        assert cmd.topic == "AI发展趋势"
        assert cmd.variant_count == 3  # default

    def test_full_command(self):
        text = "#视频 量子计算入门 [视角数:5] [平台:抖音,B站,小红书] [风格:科技感]"
        cmd = parse_command(text)
        assert cmd is not None
        assert cmd.topic == "量子计算入门"
        assert cmd.variant_count == 5
        assert Platform.DOUYIN in cmd.platforms
        assert Platform.BILIBILI in cmd.platforms
        assert Platform.XIAOHONGSHU in cmd.platforms
        assert cmd.style == "科技感"

    def test_engine_selection(self):
        text = "#视频 美食制作 [引擎:小云雀]"
        cmd = parse_command(text)
        assert cmd is not None
        assert cmd.engine == VideoEngine.XIAOYUNQUE

    def test_non_command_returns_none(self):
        assert parse_command("你好") is None
        assert parse_command("# 视频") is None
        assert parse_command("") is None


class TestParseConfirmation:
    """测试用户确认/换主题消息解析."""

    def test_confirm(self):
        text = "#确认 abc123"
        result = parse_confirmation(text)
        assert result is not None
        assert result.workflow_id == "abc123"
        assert result.action == "confirm"

    def test_change_topic(self):
        text = "#换主题 abc123 猫咪迷惑行为大赏"
        result = parse_confirmation(text)
        assert result is not None
        assert result.workflow_id == "abc123"
        assert result.action == "change"
        assert result.new_topic == "猫咪迷惑行为大赏"

    def test_recommend_selection(self):
        text = "#推荐2 abc123"
        result = parse_confirmation(text)
        assert result is not None
        assert result.workflow_id == "abc123"
        assert result.action == "recommend"
        assert result.recommend_index == 2

    def test_non_confirmation_returns_none(self):
        assert parse_confirmation("你好") is None
        assert parse_confirmation("#视频 AI") is None
        assert parse_confirmation("") is None
