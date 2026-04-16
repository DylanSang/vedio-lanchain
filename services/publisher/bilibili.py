"""B站视频发布 — 通过 B站开放平台投稿 API 上传并发布.

API 流程: 预上传 -> 分片上传 -> 提交投稿
使用 SESSDATA + bili_jct (CSRF) cookie 认证.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from config import settings
from models.schemas import Platform, PublishResult

from .base import BasePublisher, VideoMetadata

logger = logging.getLogger(__name__)

_PREUPLOAD_URL = "https://member.bilibili.com/preupload"
_ADD_URL = "https://member.bilibili.com/x/vu/web/add/v3"


class BilibiliPublisher(BasePublisher):
    platform = Platform.BILIBILI

    def __init__(self) -> None:
        self._sessdata = settings.bilibili.sessdata
        self._csrf = settings.bilibili.bili_jct
        self._http = httpx.AsyncClient(
            timeout=300,
            cookies={"SESSDATA": self._sessdata, "bili_jct": self._csrf},
            headers={"Referer": "https://member.bilibili.com/"},
        )

    async def publish(self, video_path: Path, metadata: VideoMetadata) -> PublishResult:
        try:
            upload_info = await self._preupload(video_path)
            await self._upload_chunks(video_path, upload_info)
            url = await self._submit(upload_info, metadata)
            return self._success(url)
        except Exception as e:
            return self._fail(str(e))

    async def _preupload(self, video_path: Path) -> dict:
        params = {
            "name": video_path.name,
            "size": video_path.stat().st_size,
            "r": "upos",
            "profile": "ugcfx/bup",
        }
        resp = await self._http.get(_PREUPLOAD_URL, params=params)
        resp.raise_for_status()
        return resp.json()

    async def _upload_chunks(self, video_path: Path, info: dict) -> None:
        upload_url = info.get("url", "")
        auth = info.get("auth", "")
        biz_id = info.get("biz_id", "")
        chunk_size = info.get("chunk_size", 4 * 1024 * 1024)

        file_size = video_path.stat().st_size
        chunks = (file_size + chunk_size - 1) // chunk_size

        with open(video_path, "rb") as f:
            for i in range(chunks):
                chunk = f.read(chunk_size)
                params = {
                    "partNumber": i + 1,
                    "uploadId": info.get("upload_id", ""),
                    "chunk": i,
                    "chunks": chunks,
                    "size": len(chunk),
                    "start": i * chunk_size,
                    "end": i * chunk_size + len(chunk),
                    "total": file_size,
                }
                headers = {"X-Upos-Auth": auth}
                await self._http.put(
                    upload_url, params=params, content=chunk, headers=headers
                )
                logger.debug("B站上传分片: %d/%d", i + 1, chunks)

    async def _submit(self, info: dict, metadata: VideoMetadata) -> str:
        body = {
            "csrf": self._csrf,
            "videos": [{
                "filename": info.get("upos_uri", "").split("//")[-1].split(".")[0],
                "title": metadata.title,
                "desc": metadata.description,
            }],
            "title": metadata.title,
            "desc": metadata.description,
            "tag": ",".join(metadata.tags[:12]),
            "tid": 21,  # 日常分区
            "copyright": 1,
            "source": "",
            "cover": metadata.cover_path,
        }
        resp = await self._http.post(
            _ADD_URL,
            json=body,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        bvid = data.get("data", {}).get("bvid", "")
        return f"https://www.bilibili.com/video/{bvid}" if bvid else ""

    async def close(self) -> None:
        await self._http.aclose()
