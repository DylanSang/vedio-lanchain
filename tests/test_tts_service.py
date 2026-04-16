"""TTS 配音服务单元测试."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path

from services.tts_service import TTSSegment, generate_tts_for_scenes, _safe_name


class TestSafeName:
    def test_replaces_special_chars(self):
        assert _safe_name("hello/world:test") == "hello_world_test"

    def test_limits_length(self):
        assert len(_safe_name("a" * 50)) <= 20


class TestGenerateTTSForScenes:
    @pytest.mark.asyncio
    async def test_empty_narration_skipped(self):
        scenes = [{"scene_id": 1, "narration": "", "duration": 5.0}]
        with patch("services.tts_service._generate_edge_tts"):
            result = await generate_tts_for_scenes(scenes, "test", "v1")
        assert len(result) == 1
        assert result[0].text == ""
        assert result[0].duration == 0.0

    @pytest.mark.asyncio
    async def test_returns_correct_segments(self):
        scenes = [
            {"scene_id": 1, "narration": "你好世界", "duration": 5.0},
            {"scene_id": 2, "narration": "测试文本", "duration": 3.0},
        ]
        with patch("services.tts_service._generate_edge_tts", new_callable=AsyncMock, return_value=4.0):
            with patch("services.tts_service._adjust_duration", side_effect=lambda p, *a: p):
                result = await generate_tts_for_scenes(scenes, "topic", "variant")
        assert len(result) == 2
        assert result[0].scene_id == 1
        assert result[1].scene_id == 2
