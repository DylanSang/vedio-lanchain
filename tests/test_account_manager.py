"""多账号管理模块单测."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from models.schemas import Platform
from services.account_manager import AccountManager, PlatformAccount


class TestPlatformAccount:
    def test_default_values(self):
        acc = PlatformAccount(
            platform=Platform.DOUYIN,
            account_id="acc_1",
            name="测试号",
        )
        assert acc.enabled is True
        assert acc.published_hashes == set()
        assert acc.credentials == {}


class TestAccountManager:
    def test_empty_init(self):
        mgr = AccountManager()
        assert mgr.get_accounts(Platform.DOUYIN) == []

    def test_add_and_get_accounts(self):
        mgr = AccountManager()
        a1 = PlatformAccount(platform=Platform.DOUYIN, account_id="1", name="抖音号1")
        a2 = PlatformAccount(platform=Platform.DOUYIN, account_id="2", name="抖音号2")
        a3 = PlatformAccount(platform=Platform.BILIBILI, account_id="3", name="B站号1")
        mgr.add_account(a1)
        mgr.add_account(a2)
        mgr.add_account(a3)

        assert len(mgr.get_accounts(Platform.DOUYIN)) == 2
        assert len(mgr.get_accounts(Platform.BILIBILI)) == 1
        assert mgr.get_accounts(Platform.XIAOHONGSHU) == []

    def test_disabled_account_excluded(self):
        mgr = AccountManager()
        a1 = PlatformAccount(platform=Platform.DOUYIN, account_id="1", name="启用号", enabled=True)
        a2 = PlatformAccount(platform=Platform.DOUYIN, account_id="2", name="禁用号", enabled=False)
        mgr.add_account(a1)
        mgr.add_account(a2)

        accounts = mgr.get_accounts(Platform.DOUYIN)
        assert len(accounts) == 1
        assert accounts[0].name == "启用号"

    def test_select_account_dedup(self):
        mgr = AccountManager()
        a1 = PlatformAccount(platform=Platform.DOUYIN, account_id="1", name="号A")
        a2 = PlatformAccount(platform=Platform.DOUYIN, account_id="2", name="号B")
        mgr.add_account(a1)
        mgr.add_account(a2)

        first = mgr.select_account(Platform.DOUYIN, "标题1", "描述1")
        assert first is not None
        assert first.name == "号A"

        second = mgr.select_account(Platform.DOUYIN, "标题1", "描述1")
        assert second is not None
        assert second.name == "号B"

    def test_select_account_all_published_returns_first(self):
        mgr = AccountManager()
        a1 = PlatformAccount(platform=Platform.DOUYIN, account_id="1", name="唯一号")
        mgr.add_account(a1)

        mgr.select_account(Platform.DOUYIN, "标题", "描述")
        again = mgr.select_account(Platform.DOUYIN, "标题", "描述")
        assert again.name == "唯一号"

    def test_select_account_no_accounts(self):
        mgr = AccountManager()
        assert mgr.select_account(Platform.DOUYIN, "t", "d") is None

    def test_assign_variants(self):
        mgr = AccountManager()
        a1 = PlatformAccount(platform=Platform.DOUYIN, account_id="1", name="号A")
        a2 = PlatformAccount(platform=Platform.DOUYIN, account_id="2", name="号B")
        mgr.add_account(a1)
        mgr.add_account(a2)

        result = mgr.assign_variants(Platform.DOUYIN, [1, 2, 3], ["t1", "t2", "t3"])
        assert result[1].name == "号A"
        assert result[2].name == "号B"
        assert result[3].name == "号A"

    def test_load_config(self, tmp_path: Path):
        config = {
            "accounts": [
                {
                    "platform": "douyin",
                    "account_id": "acc_1",
                    "name": "配置号",
                    "enabled": True,
                    "credentials": {"token": "xxx"},
                },
            ],
        }
        config_file = tmp_path / "accounts.json"
        config_file.write_text(json.dumps(config), encoding="utf-8")

        mgr = AccountManager(config_path=config_file)
        accounts = mgr.get_accounts(Platform.DOUYIN)
        assert len(accounts) == 1
        assert accounts[0].name == "配置号"
        assert accounts[0].credentials == {"token": "xxx"}
