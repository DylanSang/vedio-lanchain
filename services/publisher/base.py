"""平台发布器基类."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from models.schemas import Platform, PublishResult

logger = logging.getLogger(__name__)


class VideoMetadata:
    """视频发布所需的元数据."""

    def __init__(
        self,
        title: str,
        description: str = "",
        tags: list[str] | None = None,
        cover_path: str = "",
    ) -> None:
        self.title = title
        self.description = description
        self.tags = tags or []
        self.cover_path = cover_path


class BasePublisher(ABC):
    """视频发布器抽象基类."""

    platform: Platform

    @abstractmethod
    async def publish(self, video_path: Path, metadata: VideoMetadata) -> PublishResult:
        """发布视频到平台.

        Args:
            video_path: 本地视频文件路径
            metadata: 视频元数据 (标题、描述、标签)

        Returns:
            发布结果
        """

    async def close(self) -> None:
        """清理资源."""

    def _success(self, url: str, variant_id: int = 0) -> PublishResult:
        return PublishResult(
            platform=self.platform,
            success=True,
            url=url,
            variant_id=variant_id,
        )

    def _fail(self, error: str, variant_id: int = 0) -> PublishResult:
        logger.error("[%s] 发布失败: %s", self.platform.value, error)
        return PublishResult(
            platform=self.platform,
            success=False,
            error=error,
            variant_id=variant_id,
        )
