"""抖音视频发布 — 通过抖音开放平台 API 上传并发布视频.

文档: https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/video-management/douyin/create/upload
流程: 上传视频 -> 创建发布 -> 获取发布结果
"""
from __future__ import annotations

import logging
from pathlib import Path

import httpx

from config import settings
from models.schemas import Platform, PublishResult

from .base import BasePublisher, VideoMetadata

logger = logging.getLogger(__name__)

_UPLOAD_URL = "https://open.douyin.com/api/douyin/v1/video/upload_video/"
_CREATE_URL = "https://open.douyin.com/api/douyin/v1/video/create_video/"


class DouyinPublisher(BasePublisher):
    platform = Platform.DOUYIN

    def __init__(self) -> None:
        self._token = settings.douyin.access_token
        self._http = httpx.AsyncClient(timeout=300)

    async def publish(self, video_path: Path, metadata: VideoMetadata) -> PublishResult:
        try:
            video_id = await self._upload(video_path)
            url = await self._create(video_id, metadata)
            return self._success(url)
        except Exception as e:
            return self._fail(str(e))

    async def _upload(self, video_path: Path) -> str:
        headers = {"access-token": self._token}
        with open(video_path, "rb") as f:
            files = {"video": (video_path.name, f, "video/mp4")}
            resp = await self._http.post(_UPLOAD_URL, headers=headers, files=files)
        resp.raise_for_status()
        data = resp.json()
        if data.get("data", {}).get("error_code", 0) != 0:
            raise RuntimeError(f"抖音上传失败: {data}")
        return data["data"]["video"]["video_id"]

    async def _create(self, video_id: str, metadata: VideoMetadata) -> str:
        headers = {
            "access-token": self._token,
            "Content-Type": "application/json",
        }
        body = {
            "video_id": video_id,
            "text": metadata.title,
            "poi_id": "",
            "micro_app_id": "",
        }
        resp = await self._http.post(_CREATE_URL, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
        item_id = data.get("data", {}).get("item_id", "")
        return f"https://www.douyin.com/video/{item_id}" if item_id else ""

    async def close(self) -> None:
        await self._http.aclose()
