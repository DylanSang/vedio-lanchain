"""多账号矩阵管理 — 同平台多账号轮询, 变体分配到不同号, 内容去重."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from models.schemas import Platform

logger = logging.getLogger(__name__)


@dataclass
class PlatformAccount:
    """单个平台账号."""
    platform: Platform
    account_id: str
    name: str
    credentials: dict = field(default_factory=dict)
    enabled: bool = True
    published_hashes: set[str] = field(default_factory=set)


class AccountManager:
    """多账号矩阵管理器.

    负责:
    1. 管理各平台多个账号
    2. 按轮询/策略分配发布目标
    3. 内容去重 — 同一账号不发相同/高度相似内容
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self._accounts: dict[Platform, list[PlatformAccount]] = {}
        if config_path and config_path.exists():
            self._load_config(config_path)

    def _load_config(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        for item in data.get("accounts", []):
            platform = Platform(item["platform"])
            account = PlatformAccount(
                platform=platform,
                account_id=item["account_id"],
                name=item["name"],
                credentials=item.get("credentials", {}),
                enabled=item.get("enabled", True),
            )
            self._accounts.setdefault(platform, []).append(account)
        logger.info("已加载 %d 个平台的账号配置", len(self._accounts))

    def add_account(self, account: PlatformAccount) -> None:
        self._accounts.setdefault(account.platform, []).append(account)

    def get_accounts(self, platform: Platform) -> list[PlatformAccount]:
        return [a for a in self._accounts.get(platform, []) if a.enabled]

    def _content_hash(self, title: str, description: str) -> str:
        text = f"{title}|{description}"
        return hashlib.md5(text.encode()).hexdigest()[:16]

    def select_account(
        self,
        platform: Platform,
        title: str,
        description: str,
    ) -> PlatformAccount | None:
        """为指定内容选择一个合适的账号 (去重 + 轮询)."""
        accounts = self.get_accounts(platform)
        if not accounts:
            return None

        content_hash = self._content_hash(title, description)

        for account in accounts:
            if content_hash not in account.published_hashes:
                account.published_hashes.add(content_hash)
                logger.info("选择账号: [%s] %s (去重后)", platform.value, account.name)
                return account

        logger.warning("所有账号已发布相似内容: [%s] %s", platform.value, title[:30])
        return accounts[0]

    def assign_variants(
        self,
        platform: Platform,
        variant_ids: list[int],
        titles: list[str],
    ) -> dict[int, PlatformAccount | None]:
        """将多个变体分配到不同账号 (尽量分散).

        Returns:
            {variant_id: account}
        """
        accounts = self.get_accounts(platform)
        result: dict[int, PlatformAccount | None] = {}

        for i, (vid, title) in enumerate(zip(variant_ids, titles)):
            if accounts:
                result[vid] = accounts[i % len(accounts)]
            else:
                result[vid] = None

        return result
