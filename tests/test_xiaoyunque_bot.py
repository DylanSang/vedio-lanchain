"""小云雀浏览器自动化模块单测.

小云雀依赖 Playwright 浏览器, 单测仅验证类结构和异常处理,
不启动真实浏览器。
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock, PropertyMock

import pytest

from services.xiaoyunque_bot import XiaoyunqueBot, XiaoyunqueError


class TestXiaoyunqueBotInit:
    def test_initial_state(self):
        bot = XiaoyunqueBot()
        assert bot._pw is None
        assert bot._browser is None
        assert bot._context is None


class TestXiaoyunqueBotClose:
    @pytest.mark.asyncio
    async def test_close_when_nothing_opened(self):
        bot = XiaoyunqueBot()
        await bot.close()

    @pytest.mark.asyncio
    async def test_close_all_resources(self):
        bot = XiaoyunqueBot()
        bot._context = AsyncMock()
        bot._browser = AsyncMock()
        bot._pw = AsyncMock()

        await bot.close()

        bot._context.close.assert_awaited_once()
        bot._browser.close.assert_awaited_once()
        bot._pw.stop.assert_awaited_once()


class TestXiaoyunqueError:
    def test_is_exception(self):
        err = XiaoyunqueError("测试错误")
        assert isinstance(err, Exception)
        assert str(err) == "测试错误"


class TestGenerateVideo:
    @pytest.mark.asyncio
    async def test_generate_raises_on_failure(self, tmp_path: Path):
        bot = XiaoyunqueBot()

        mock_page = AsyncMock()
        mock_page.locator.return_value.first.is_visible = AsyncMock(return_value=False)
        mock_page.locator.return_value.first.click = AsyncMock(side_effect=Exception("Element not found"))
        mock_page.close = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.new_page.return_value = mock_page

        bot._context = mock_ctx

        with pytest.raises(XiaoyunqueError, match="小云雀视频生成失败"):
            await bot.generate_video("测试主题", save_dir=tmp_path)

        mock_page.close.assert_awaited_once()
