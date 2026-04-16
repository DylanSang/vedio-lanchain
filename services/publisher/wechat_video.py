"""微信视频号发布 — 通过 Playwright 浏览器自动化发布.

微信视频号 API 权限极受限，使用浏览器自动化操作视频号助手网页版:
https://channels.weixin.qq.com/platform/post/create
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from playwright.async_api import async_playwright

from config import settings
from models.schemas import Platform, PublishResult

from .base import BasePublisher, VideoMetadata

logger = logging.getLogger(__name__)

_CHANNELS_URL = "https://channels.weixin.qq.com/platform/post/create"
_STATE_FILE = settings.output_dir / ".wechat_channels_state.json"


class WechatVideoPublisher(BasePublisher):
    platform = Platform.WECHAT_VIDEO

    async def publish(self, video_path: Path, metadata: VideoMetadata) -> PublishResult:
        try:
            url = await self._browser_publish(video_path, metadata)
            return self._success(url)
        except Exception as e:
            return self._fail(str(e))

    async def _browser_publish(self, video_path: Path, metadata: VideoMetadata) -> str:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=False)

            if _STATE_FILE.exists():
                context = await browser.new_context(storage_state=str(_STATE_FILE))
            else:
                context = await browser.new_context()
                logger.warning("微信视频号未登录，请在浏览器中扫码登录")

            page = await context.new_page()
            await page.goto(_CHANNELS_URL, wait_until="networkidle")

            # 上传视频
            upload_input = page.locator('input[type="file"]').first
            await upload_input.set_input_files(str(video_path))
            logger.info("微信视频号: 视频上传中...")

            await page.wait_for_selector(
                '[class*="upload-success"], [class*="preview"], video',
                timeout=180_000,
            )

            # 填写描述 (视频号没有独立标题字段，描述即文案)
            desc_input = page.locator('[contenteditable=true], textarea').first
            desc_text = metadata.title
            if metadata.description:
                desc_text += f"\n{metadata.description}"
            if metadata.tags:
                desc_text += "\n" + " ".join(f"#{t}" for t in metadata.tags)
            await desc_input.fill(desc_text)

            # 点击发表
            pub_btn = page.locator('button:has-text("发表")').first
            await pub_btn.click()

            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)

            await context.storage_state(path=str(_STATE_FILE))

            current_url = page.url
            await browser.close()

            return current_url

    async def close(self) -> None:
        pass
