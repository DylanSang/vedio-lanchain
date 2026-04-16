"""多平台发布模块 — 工厂函数根据平台名返回对应的发布器."""
from __future__ import annotations

from models.schemas import Platform

from .base import BasePublisher, VideoMetadata
from .bilibili import BilibiliPublisher
from .douyin import DouyinPublisher
from .kuaishou import KuaishouPublisher
from .xiaohongshu import XiaohongshuPublisher
from .wechat_video import WechatVideoPublisher

_REGISTRY: dict[Platform, type[BasePublisher]] = {
    Platform.DOUYIN: DouyinPublisher,
    Platform.BILIBILI: BilibiliPublisher,
    Platform.KUAISHOU: KuaishouPublisher,
    Platform.XIAOHONGSHU: XiaohongshuPublisher,
    Platform.WECHAT_VIDEO: WechatVideoPublisher,
}


def get_publisher(platform: Platform) -> BasePublisher:
    """根据平台枚举获取对应的发布器实例."""
    cls = _REGISTRY.get(platform)
    if cls is None:
        raise ValueError(f"不支持的平台: {platform}")
    return cls()


__all__ = [
    "BasePublisher",
    "VideoMetadata",
    "get_publisher",
]
