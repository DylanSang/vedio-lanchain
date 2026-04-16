"""小红书视频发布 — 通过 Playwright 浏览器自动化发布.

小红书没有公开的视频发布 API，使用浏览器自动化实现:
1. 打开小红书创作者中心
2. 上传视频
3. 填写标题、描述、标签
4. 发布
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

_CREATOR_URL = "https://creator.xiaohongshu.com/publish/publish"
_STATE_FILE = settings.output_dir / ".xiaohongshu_state.json"


class XiaohongshuPublisher(BasePublisher):
    platform = Platform.XIAOHONGSHU

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
                logger.warning("小红书未登录，请在浏览器中手动登录")

            page = await context.new_page()
            await page.goto(_CREATOR_URL, wait_until="networkidle")

            # 上传视频文件
            upload_input = page.locator('input[type="file"]').first
            await upload_input.set_input_files(str(video_path))
            logger.info("小红书: 视频上传中...")

            await page.wait_for_selector(
                '[class*="upload-success"], [class*="preview"]',
                timeout=120_000,
            )

            # 填写标题
            title_input = page.locator('[placeholder*="标题"], [class*="title"] input').first
            await title_input.fill(metadata.title[:20])

            # 填写描述
            desc_input = page.locator(
                '[placeholder*="描述"], [placeholder*="正文"], [contenteditable=true]'
            ).first
            desc_text = metadata.description
            if metadata.tags:
                desc_text += "\n" + " ".join(f"#{t}" for t in metadata.tags)
            await desc_input.fill(desc_text)

            # 点击发布
            pub_btn = page.locator('button:has-text("发布")').first
            await pub_btn.click()

            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)

            await context.storage_state(path=str(_STATE_FILE))

            current_url = page.url
            await browser.close()

            return current_url

    async def close(self) -> None:
        pass
