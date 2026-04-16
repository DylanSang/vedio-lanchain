"""素材库管理模块单测."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from services.asset_library import AssetLibrary


@pytest.fixture
def lib(tmp_path: Path):
    """使用临时目录的 AssetLibrary 实例."""
    with patch("services.asset_library.settings") as mock_settings:
        mock_settings.output_dir = tmp_path
        mock_settings.assets_dir = tmp_path / "assets"
        mock_settings.assets_dir.mkdir()
        yield AssetLibrary()


class TestCacheVideo:
    def test_cache_and_retrieve(self, lib: AssetLibrary, tmp_path: Path):
        fake_video = tmp_path / "video.mp4"
        fake_video.write_text("fake")

        lib.cache_video("AI主题", 1, str(fake_video))
        result = lib.get_cached_video("AI主题", 1)
        assert result == str(fake_video)

    def test_cache_miss_returns_none(self, lib: AssetLibrary):
        assert lib.get_cached_video("不存在", 99) is None

    def test_cache_stale_file_returns_none(self, lib: AssetLibrary):
        lib.cache_video("主题", 1, "/nonexistent/path.mp4")
        assert lib.get_cached_video("主题", 1) is None


class TestIndexPlan:
    def test_index_and_search(self, lib: AssetLibrary):
        lib.index_plan("AI发展", "/path/plan.md", ["AI", "科技"])
        lib.index_plan("美食制作", "/path/food.md", ["美食", "烹饪"])

        results = lib.search_similar_plans("AI")
        assert len(results) == 1
        assert results[0]["topic"] == "AI发展"

    def test_search_by_tag(self, lib: AssetLibrary):
        lib.index_plan("主题A", "/a.md", ["科技", "编程"])
        results = lib.search_similar_plans("编程")
        assert len(results) == 1

    def test_search_no_match(self, lib: AssetLibrary):
        lib.index_plan("主题A", "/a.md", ["科技"])
        assert lib.search_similar_plans("美食") == []

    def test_search_limit(self, lib: AssetLibrary):
        for i in range(10):
            lib.index_plan(f"AI主题{i}", f"/p{i}.md", ["AI"])
        results = lib.search_similar_plans("AI", limit=3)
        assert len(results) == 3


class TestSearchAssets:
    def test_search_by_type(self, lib: AssetLibrary, tmp_path: Path):
        bgm_dir = tmp_path / "assets" / "bgm"
        bgm_dir.mkdir(parents=True)
        (bgm_dir / "happy.mp3").write_text("fake")
        (bgm_dir / "sad.mp3").write_text("fake")

        lib.scan_assets()
        results = lib.search_assets(asset_type="mp3")
        assert len(results) == 2

    def test_search_by_keyword(self, lib: AssetLibrary, tmp_path: Path):
        bgm_dir = tmp_path / "assets" / "bgm"
        bgm_dir.mkdir(parents=True)
        (bgm_dir / "happy_tune.mp3").write_text("fake")
        (bgm_dir / "sad_melody.mp3").write_text("fake")

        lib.scan_assets()
        results = lib.search_assets(keyword="happy")
        assert len(results) == 1
        assert "happy" in results[0]["name"]


class TestPersistence:
    def test_index_survives_reload(self, tmp_path: Path):
        with patch("services.asset_library.settings") as mock_settings:
            mock_settings.output_dir = tmp_path
            mock_settings.assets_dir = tmp_path / "assets"
            mock_settings.assets_dir.mkdir()

            lib1 = AssetLibrary()
            lib1.index_plan("持久化测试", "/p.md", ["test"])
            lib1.cache_video("持久化测试", 1, str(tmp_path / "v.mp4"))

        with patch("services.asset_library.settings") as mock_settings:
            mock_settings.output_dir = tmp_path
            mock_settings.assets_dir = tmp_path / "assets"

            lib2 = AssetLibrary()
            plans = lib2.search_similar_plans("持久化")
            assert len(plans) == 1
