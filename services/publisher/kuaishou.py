"""快手视频发布 — 通过快手开放平台 API 上传并发布.

文档: https://open.kuaishou.com/platform/openApi
流程: 上传视频 -> 创建作品
"""
from __future__ import annotations

import logging
from pathlib import Path

import httpx

from config import settings
from models.schemas import Platform, PublishResult

from .base import BasePublisher, VideoMetadata

logger = logging.getLogger(__name__)

_UPLOAD_URL = "https://open.kuaishou.com/openapi/photo/publish"


class KuaishouPublisher(BasePublisher):
    platform = Platform.KUAISHOU

    def __init__(self) -> None:
        self._token = settings.kuaishou.access_token
        self._http = httpx.AsyncClient(timeout=300)

    async def publish(self, video_path: Path, metadata: VideoMetadata) -> PublishResult:
        try:
            url = await self._upload_and_publish(video_path, metadata)
            return self._success(url)
        except Exception as e:
            return self._fail(str(e))

    async def _upload_and_publish(self, video_path: Path, metadata: VideoMetadata) -> str:
        headers = {"access_token": self._token}
        with open(video_path, "rb") as f:
            files = {"file": (video_path.name, f, "video/mp4")}
            data = {
                "caption": metadata.title,
                "tags": ",".join(metadata.tags[:5]),
            }
            resp = await self._http.post(
                _UPLOAD_URL, headers=headers, files=files, data=data
            )
        resp.raise_for_status()
        result = resp.json()
        if result.get("result") != 1:
            raise RuntimeError(f"快手发布失败: {result}")
        photo_id = result.get("photo_id", "")
        return f"https://www.kuaishou.com/short-video/{photo_id}" if photo_id else ""

    async def close(self) -> None:
        await self._http.aclose()
