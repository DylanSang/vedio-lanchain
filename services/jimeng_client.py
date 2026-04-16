"""即梦 API 客户端 — 封装火山引擎即梦视频生成 3.0 Pro 的提交/轮询/下载流程.

火山引擎即梦 API 文档:
- 视频生成 3.0 Pro: https://www.volcengine.com/docs/85621/1777001
- 文生图 seedream: https://www.volcengine.com/docs/85621/1616429

API 采用异步任务模式:
  1. 提交生成任务 -> 获得 task_id
  2. 轮询任务状态 -> 等待完成
  3. 获取结果 (视频/图片 URL) -> 下载到本地
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://visual.volcengineapi.com"
_SERVICE = "cv"
_REGION = "cn-north-1"
_VERSION = "2022-08-31"

_TEXT2IMG_ACTION = "CVProcess"
_VIDEO_GEN_ACTION = "CVProcess"


class JimengError(Exception):
    pass


class JimengClient:
    """火山引擎即梦 API 异步客户端."""

    def __init__(self) -> None:
        self.ak = settings.volcengine.access_key
        self.sk = settings.volcengine.secret_key
        self._http = httpx.AsyncClient(timeout=120)

    # ── 签名 ──

    def _sign(self, method: str, path: str, query: dict, headers: dict, body: bytes) -> dict:
        """火山引擎 V4 签名 (HMAC-SHA256)."""
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y%m%dT%H%M%SZ")
        date_short = now.strftime("%Y%m%d")

        headers["x-date"] = date_str
        headers["host"] = "visual.volcengineapi.com"

        signed_headers = ";".join(sorted(headers.keys()))
        canonical_headers = "\n".join(f"{k}:{headers[k]}" for k in sorted(headers.keys())) + "\n"

        payload_hash = hashlib.sha256(body).hexdigest()

        qs = "&".join(f"{k}={v}" for k, v in sorted(query.items()))
        canonical_request = "\n".join([method, path, qs, canonical_headers, signed_headers, payload_hash])

        credential_scope = f"{date_short}/{_REGION}/{_SERVICE}/request"
        string_to_sign = "\n".join([
            "HMAC-SHA256",
            date_str,
            credential_scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ])

        def _hmac_sha256(key: bytes, msg: str) -> bytes:
            return hmac.new(key, msg.encode(), hashlib.sha256).digest()

        k_date = _hmac_sha256(self.sk.encode(), date_short)
        k_region = _hmac_sha256(k_date, _REGION)
        k_service = _hmac_sha256(k_region, _SERVICE)
        k_signing = _hmac_sha256(k_service, "request")

        signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()

        authorization = (
            f"HMAC-SHA256 Credential={self.ak}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        headers["authorization"] = authorization
        return headers

    # ── API 调用 ──

    async def _call_api(self, action: str, body: dict) -> dict:
        """统一 API 调用入口."""
        import json as _json

        query = {"Action": action, "Version": _VERSION}
        body_bytes = _json.dumps(body).encode()

        headers: dict[str, str] = {"content-type": "application/json"}
        headers = self._sign("POST", "/", query, headers, body_bytes)

        qs = "&".join(f"{k}={v}" for k, v in query.items())
        url = f"{_BASE_URL}/?{qs}"

        resp = await self._http.post(url, content=body_bytes, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        if data.get("ResponseMetadata", {}).get("Error"):
            err = data["ResponseMetadata"]["Error"]
            raise JimengError(f"API 错误: {err.get('Code')} - {err.get('Message')}")

        return data

    # ── 文生图 ──

    async def text_to_image(
        self,
        prompt: str,
        width: int = 1280,
        height: int = 720,
        model: str = "seedream-3.0",
    ) -> str:
        """文生图，返回图片 URL."""
        body = {
            "req_key": f"i2i_{model}",
            "prompt": prompt,
            "width": width,
            "height": height,
            "model_version": model,
            "return_url": True,
            "logo_info": {"add_logo": False},
        }

        data = await self._call_api(_TEXT2IMG_ACTION, body)
        images = data.get("data", {}).get("image_urls", [])
        if not images:
            binary = data.get("data", {}).get("binary_data_base64", [])
            if binary:
                return f"base64:{binary[0]}"
            raise JimengError("文生图未返回图片")
        return images[0]

    # ── 视频生成 (异步任务) ──

    async def submit_video_task(
        self,
        prompt: str,
        image_url: str = "",
        duration: float = 5.0,
        model: str = "video-gen-3.0-pro",
    ) -> str:
        """提交视频生成任务，返回 task_id."""
        body: dict[str, Any] = {
            "req_key": f"jimeng_{model}",
            "prompt": prompt,
            "duration": int(duration),
            "model_version": model,
        }
        if image_url:
            body["image_url"] = image_url

        data = await self._call_api(_VIDEO_GEN_ACTION, body)
        task_id = data.get("data", {}).get("task_id", "")
        if not task_id:
            raise JimengError("视频生成未返回 task_id")
        logger.info("视频任务已提交: task_id=%s", task_id)
        return task_id

    async def query_video_task(self, task_id: str) -> dict:
        """查询视频任务状态."""
        body = {"req_key": "jimeng_video_query", "task_id": task_id}
        data = await self._call_api(_VIDEO_GEN_ACTION, body)
        return data.get("data", {})

    async def wait_for_video(
        self,
        task_id: str,
        poll_interval: float = 10.0,
        timeout: float = 600.0,
    ) -> str:
        """轮询等待视频生成完成，返回视频 URL."""
        start = time.monotonic()
        while True:
            if time.monotonic() - start > timeout:
                raise JimengError(f"视频生成超时 ({timeout}s): {task_id}")

            result = await self.query_video_task(task_id)
            status = result.get("status", "")

            if status == "done":
                video_url = result.get("video_url", "")
                if not video_url:
                    urls = result.get("video_urls", [])
                    video_url = urls[0] if urls else ""
                if not video_url:
                    raise JimengError(f"视频完成但无 URL: {task_id}")
                logger.info("视频生成完成: %s", task_id)
                return video_url

            if status == "failed":
                raise JimengError(f"视频生成失败: {task_id} - {result.get('error', '')}")

            logger.debug("视频生成中: %s status=%s", task_id, status)
            await asyncio.sleep(poll_interval)

    async def download_video(self, url: str, save_path: Path) -> Path:
        """下载视频到本地文件."""
        save_path.parent.mkdir(parents=True, exist_ok=True)
        async with self._http.stream("GET", url) as resp:
            resp.raise_for_status()
            with open(save_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=8192):
                    f.write(chunk)
        logger.info("视频已下载: %s", save_path)
        return save_path

    # ── 高层接口: prompt -> 本地视频文件 ──

    async def generate_video_from_prompt(
        self,
        prompt: str,
        save_dir: Path,
        filename: str,
        use_keyframe: bool = True,
        duration: float = 5.0,
    ) -> Path:
        """完整流程: 文本 -> (可选)生成关键帧图 -> 提交视频任务 -> 等待 -> 下载.

        Args:
            prompt: 画面描述 (英文)
            save_dir: 视频保存目录
            filename: 视频文件名 (不含扩展名)
            use_keyframe: 是否先生成关键帧图再做图生视频
            duration: 视频时长

        Returns:
            本地视频文件路径
        """
        image_url = ""
        if use_keyframe:
            logger.info("生成关键帧图: %s", prompt[:60])
            image_url = await self.text_to_image(prompt)

        task_id = await self.submit_video_task(
            prompt=prompt,
            image_url=image_url,
            duration=duration,
        )

        video_url = await self.wait_for_video(task_id)

        save_path = save_dir / f"{filename}.mp4"
        return await self.download_video(video_url, save_path)

    async def close(self) -> None:
        await self._http.aclose()
