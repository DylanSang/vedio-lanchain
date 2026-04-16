"""小云雀浏览器自动化 — 通过 Playwright 操作小云雀 Web 端生成视频.

小云雀 (xyq.jianying.com) 没有公开 API，因此通过浏览器自动化实现:
1. 打开小云雀网站并登录
2. 输入主题/文案
3. 等待视频生成完成
4. 下载生成的视频

注意: 首次使用需要手动扫码登录，后续使用已保存的 cookies。
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from config import settings

logger = logging.getLogger(__name__)

_XYQ_URL = "https://xyq.jianying.com"
_STATE_FILE = settings.output_dir / ".xiaoyunque_state.json"


class XiaoyunqueError(Exception):
    pass


class XiaoyunqueBot:
    """小云雀浏览器自动化客户端."""

    def __init__(self) -> None:
        self._pw = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def _ensure_browser(self) -> BrowserContext:
        if self._context is not None:
            return self._context

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=False)

        if _STATE_FILE.exists():
            self._context = await self._browser.new_context(storage_state=str(_STATE_FILE))
            logger.info("已加载小云雀登录状态")
        else:
            self._context = await self._browser.new_context()
            logger.info("未发现登录状态，首次使用需手动登录")

        return self._context

    async def _get_page(self) -> Page:
        ctx = await self._ensure_browser()
        page = await ctx.new_page()
        await page.goto(_XYQ_URL, wait_until="networkidle")
        return page

    async def login_interactive(self) -> None:
        """交互式登录 — 启动浏览器等待用户手动扫码."""
        ctx = await self._ensure_browser()
        page = await ctx.new_page()
        await page.goto(_XYQ_URL, wait_until="networkidle")

        if settings.xiaoyunque.phone:
            logger.info("配置的小云雀手机号: %s", settings.xiaoyunque.phone)
        logger.info("请在浏览器中完成登录，登录完成后按 Enter 继续...")
        await asyncio.get_running_loop().run_in_executor(None, input, "登录完成后按 Enter: ")

        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        await ctx.storage_state(path=str(_STATE_FILE))
        logger.info("登录状态已保存到 %s", _STATE_FILE)
        await page.close()

    async def generate_video(
        self,
        topic: str,
        style: str = "",
        save_dir: Path | None = None,
        filename: str = "xiaoyunque_video",
    ) -> Path:
        """通过小云雀生成视频.

        Args:
            topic: 视频主题/文案
            style: 风格偏好
            save_dir: 保存目录
            filename: 文件名 (不含扩展名)

        Returns:
            本地视频文件路径
        """
        if save_dir is None:
            save_dir = settings.videos_dir

        page = await self._get_page()
        try:
            # 点击"智能生视频"或创作入口
            create_btn = page.locator('text="智能生视频"').first
            if await create_btn.is_visible():
                await create_btn.click()
                await page.wait_for_load_state("networkidle")

            # 输入主题文案
            textarea = page.locator("textarea, [contenteditable=true]").first
            await textarea.click()
            full_text = topic
            if style:
                full_text = f"{topic}，风格: {style}"
            await textarea.fill(full_text)

            # 点击生成按钮
            gen_btn = page.locator('button:has-text("生成"), button:has-text("创作")').first
            await gen_btn.click()

            logger.info("小云雀视频生成中，等待完成...")

            # 等待视频生成完成 (最长 10 分钟)
            await page.wait_for_selector(
                '[class*="video-player"], video, [class*="result"]',
                timeout=600_000,
            )

            # 等待下载按钮出现并点击
            download_btn = page.locator('button:has-text("下载"), a:has-text("下载")').first
            await download_btn.wait_for(timeout=30_000)

            save_dir.mkdir(parents=True, exist_ok=True)
            save_path = save_dir / f"{filename}.mp4"

            async with page.expect_download() as download_info:
                await download_btn.click()
            download = await download_info.value
            await download.save_as(str(save_path))

            logger.info("小云雀视频已下载: %s", save_path)
            return save_path

        except Exception as e:
            logger.error("小云雀视频生成失败: %s", e)
            raise XiaoyunqueError(f"小云雀视频生成失败: {e}") from e
        finally:
            await page.close()

    async def close(self) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
