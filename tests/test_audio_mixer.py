"""音频处理链单元测试."""
from pathlib import Path
from unittest.mock import patch, MagicMock

from services.audio_mixer import concat_tts_segments, normalize_audio
from services.tts_service import TTSSegment


class TestConcatTTSSegments:
    def test_no_valid_segments(self, tmp_path):
        segs = [TTSSegment(scene_id=1, text="", audio_path=Path(""), duration=0, target_duration=5)]
        result = concat_tts_segments(segs, tmp_path / "out.mp3")
        assert result is None

    def test_valid_segments(self, tmp_path):
        audio_file = tmp_path / "tts_01.mp3"
        audio_file.write_bytes(b"fake audio")
        seg = TTSSegment(scene_id=1, text="hi", audio_path=audio_file, duration=3, target_duration=5)

        with patch("services.audio_mixer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            concat_path = tmp_path / "out.mp3"
            concat_path.write_bytes(b"concat")
            result = concat_tts_segments([seg], concat_path)
        assert result is not None


class TestNormalizeAudio:
    def test_normalization(self, tmp_path):
        input_file = tmp_path / "in.aac"
        input_file.write_bytes(b"audio")
        output_file = tmp_path / "out.aac"

        with patch("services.audio_mixer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            output_file.write_bytes(b"normalized")
            result = normalize_audio(input_file, output_file)
        assert result == output_file
