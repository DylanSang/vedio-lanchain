"""方案导出模块单测."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from models.schemas import ContentPlan, ContentVariant, Platform, SceneScript
from services.plan_exporter import _safe_filename, _render_variant_md, export_plan


class TestSafeFilename:
    def test_removes_special_chars(self):
        assert _safe_filename('hello/world:test?') == "hello_world_test"

    def test_truncates_to_max_len(self):
        assert len(_safe_filename("a" * 100, max_len=20)) <= 20

    def test_strips_trailing_underscore(self):
        result = _safe_filename("hello_")
        assert not result.endswith("_")

    def test_chinese_chars_preserved(self):
        result = _safe_filename("AI发展趋势")
        assert "AI发展趋势" == result


def _make_variant(variant_id: int = 1) -> ContentVariant:
    return ContentVariant(
        variant_id=variant_id,
        perspective="科普讲解",
        title="AI入门",
        description="科普视角",
        scenes=[
            SceneScript(scene_id=1, prompt="A robot waving", duration=5.0, narration="你好"),
            SceneScript(scene_id=2, prompt="Timeline", duration=8.0, narration=""),
        ],
        tags=["AI", "科技"],
        target_platforms=[Platform.DOUYIN],
    )


def _make_plan() -> ContentPlan:
    return ContentPlan(
        topic="AI发展趋势",
        variants=[_make_variant(1), _make_variant(2)],
    )


class TestRenderVariantMd:
    def test_contains_title(self):
        md = _render_variant_md(_make_variant(), "AI发展趋势")
        assert "# AI入门" in md

    def test_contains_scenes(self):
        md = _render_variant_md(_make_variant(), "AI发展趋势")
        assert "分镜 1" in md
        assert "分镜 2" in md

    def test_narration_only_for_nonempty(self):
        md = _render_variant_md(_make_variant(), "AI发展趋势")
        assert "你好" in md
        lines = md.split("\n")
        narration_count = sum(1 for l in lines if "旁白文案" in l)
        assert narration_count == 1

    def test_total_duration(self):
        md = _render_variant_md(_make_variant(), "AI发展趋势")
        assert "13.0s" in md


class TestExportPlan:
    def test_exports_correct_number_of_files(self, tmp_path: Path):
        with patch("services.plan_exporter.settings") as mock_settings:
            mock_settings.plans_dir = tmp_path
            plan = _make_plan()
            files = export_plan(plan)
            assert len(files) == 2
            assert all(f.exists() for f in files)
            assert all(f.suffix == ".md" for f in files)

    def test_file_content_valid_markdown(self, tmp_path: Path):
        with patch("services.plan_exporter.settings") as mock_settings:
            mock_settings.plans_dir = tmp_path
            plan = _make_plan()
            files = export_plan(plan)
            content = files[0].read_text(encoding="utf-8")
            assert "# AI入门" in content
            assert "AI发展趋势" in content
