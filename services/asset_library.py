"""素材库管理 — 视频/图片/音乐素材索引检索, 相似主题缓存复用, 历史方案参考."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)


class AssetLibrary:
    """本地素材库索引与检索.

    功能:
    1. 扫描并索引 assets/ 下所有素材文件
    2. 按类型/标签/关键词检索
    3. 视频生成结果缓存 — 相同主题避免重复生成
    4. 历史方案参考 — 检索过往方案辅助新方案生成
    """

    def __init__(self) -> None:
        self._index_path = settings.output_dir / "asset_index.json"
        self._index: dict = self._load_index()

    def _load_index(self) -> dict:
        if self._index_path.exists():
            try:
                return json.loads(self._index_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"assets": [], "cache": {}, "plans": []}

    def _save_index(self) -> None:
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        self._index_path.write_text(
            json.dumps(self._index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def scan_assets(self) -> int:
        """扫描 assets/ 目录, 更新素材索引."""
        assets_dir = settings.assets_dir
        entries: list[dict] = []

        for ext in ("*.mp3", "*.wav", "*.mp4", "*.mov", "*.png", "*.jpg", "*.ttf"):
            for f in assets_dir.rglob(ext):
                entries.append({
                    "path": str(f.relative_to(assets_dir)),
                    "type": f.suffix[1:],
                    "category": f.parent.name,
                    "name": f.stem,
                    "size": f.stat().st_size,
                    "indexed_at": datetime.now().isoformat(),
                })

        self._index["assets"] = entries
        self._save_index()
        logger.info("素材库扫描完成: %d 个文件", len(entries))
        return len(entries)

    def search_assets(
        self,
        asset_type: str | None = None,
        category: str | None = None,
        keyword: str | None = None,
    ) -> list[dict]:
        """按条件检索素材."""
        results = self._index.get("assets", [])

        if asset_type:
            results = [a for a in results if a["type"] == asset_type]
        if category:
            results = [a for a in results if a["category"] == category]
        if keyword:
            kw = keyword.lower()
            results = [a for a in results if kw in a["name"].lower() or kw in a.get("category", "").lower()]

        return results

    def cache_video(self, topic: str, variant_id: int, video_path: str) -> None:
        """缓存视频生成结果, 相同主题可复用."""
        key = f"{topic}_{variant_id}"
        self._index.setdefault("cache", {})[key] = {
            "path": video_path,
            "cached_at": datetime.now().isoformat(),
        }
        self._save_index()

    def get_cached_video(self, topic: str, variant_id: int) -> str | None:
        """查找主题的缓存视频."""
        key = f"{topic}_{variant_id}"
        entry = self._index.get("cache", {}).get(key)
        if entry and Path(entry["path"]).exists():
            logger.info("命中缓存: %s -> %s", key, entry["path"])
            return entry["path"]
        return None

    def index_plan(self, topic: str, plan_path: str, tags: list[str]) -> None:
        """索引内容方案, 支持后续检索参考."""
        self._index.setdefault("plans", []).append({
            "topic": topic,
            "path": plan_path,
            "tags": tags,
            "indexed_at": datetime.now().isoformat(),
        })
        self._save_index()

    def search_similar_plans(self, keyword: str, limit: int = 5) -> list[dict]:
        """检索相关历史方案."""
        kw = keyword.lower()
        plans = self._index.get("plans", [])
        matched = [
            p for p in plans
            if kw in p["topic"].lower() or any(kw in t.lower() for t in p.get("tags", []))
        ]
        return matched[:limit]
