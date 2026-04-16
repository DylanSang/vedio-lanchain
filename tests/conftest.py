"""Pytest 配置: 在未安装 playwright 时注册桩模块, 避免 publisher 包导入失败."""
from __future__ import annotations

import sys
import types


class _StubClass:
    """Playwright 桩类, 用于类型注解, 不可实例化调用."""
    pass


if "playwright.async_api" not in sys.modules:
    _async_api = types.ModuleType("playwright.async_api")

    async def _async_playwright() -> None:  # pragma: no cover
        raise RuntimeError("playwright stub: install playwright for real publisher tests")

    _async_api.async_playwright = _async_playwright
    _async_api.Browser = type("Browser", (_StubClass,), {})
    _async_api.BrowserContext = type("BrowserContext", (_StubClass,), {})
    _async_api.Page = type("Page", (_StubClass,), {})
    sys.modules["playwright.async_api"] = _async_api
if "playwright" not in sys.modules:
    sys.modules["playwright"] = types.ModuleType("playwright")
