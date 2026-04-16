from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


class FeishuConfig(BaseSettings):
    app_id: str = Field(default="", alias="FEISHU_APP_ID")
    app_secret: str = Field(default="", alias="FEISHU_APP_SECRET")


class LLMConfig(BaseSettings):
    api_key: str = Field(default="", alias="OPENAI_API_KEY")
    base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    model: str = Field(default="gpt-4", alias="OPENAI_MODEL")


class VolcengineConfig(BaseSettings):
    access_key: str = Field(default="", alias="VOLCENGINE_ACCESS_KEY")
    secret_key: str = Field(default="", alias="VOLCENGINE_SECRET_KEY")


class XiaoyunqueConfig(BaseSettings):
    phone: str = Field(default="", alias="XIAOYUNQUE_PHONE")


class DouyinConfig(BaseSettings):
    client_key: str = Field(default="", alias="DOUYIN_CLIENT_KEY")
    client_secret: str = Field(default="", alias="DOUYIN_CLIENT_SECRET")
    access_token: str = Field(default="", alias="DOUYIN_ACCESS_TOKEN")


class BilibiliConfig(BaseSettings):
    sessdata: str = Field(default="", alias="BILIBILI_SESSDATA")
    bili_jct: str = Field(default="", alias="BILIBILI_BILI_JCT")


class KuaishouConfig(BaseSettings):
    app_id: str = Field(default="", alias="KUAISHOU_APP_ID")
    app_secret: str = Field(default="", alias="KUAISHOU_APP_SECRET")
    access_token: str = Field(default="", alias="KUAISHOU_ACCESS_TOKEN")


class TTSConfig(BaseSettings):
    engine: str = Field(default="edge-tts", alias="TTS_ENGINE")
    voice: str = Field(default="zh-CN-XiaoxiaoNeural", alias="TTS_VOICE")


class Settings(BaseSettings):
    feishu: FeishuConfig = FeishuConfig()
    llm: LLMConfig = LLMConfig()
    volcengine: VolcengineConfig = VolcengineConfig()
    xiaoyunque: XiaoyunqueConfig = XiaoyunqueConfig()
    douyin: DouyinConfig = DouyinConfig()
    bilibili: BilibiliConfig = BilibiliConfig()
    kuaishou: KuaishouConfig = KuaishouConfig()
    tts: TTSConfig = TTSConfig()

    output_dir: Path = Field(default=BASE_DIR / "output", alias="OUTPUT_DIR")
    assets_dir: Path = Field(default=BASE_DIR / "assets", alias="ASSETS_DIR")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    default_variant_count: int = Field(default=3, alias="DEFAULT_VARIANT_COUNT")

    def _ensure(self, d: Path) -> Path:
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def plans_dir(self) -> Path:
        return self._ensure(self.output_dir / "plans")

    @property
    def videos_dir(self) -> Path:
        return self._ensure(self.output_dir / "videos")

    @property
    def audio_dir(self) -> Path:
        return self._ensure(self.output_dir / "audio")

    @property
    def thumbnails_dir(self) -> Path:
        return self._ensure(self.output_dir / "thumbnails")

    @property
    def drafts_dir(self) -> Path:
        return self._ensure(self.output_dir / "drafts")

    @property
    def bgm_dir(self) -> Path:
        return self._ensure(self.assets_dir / "bgm")

    @property
    def fonts_dir(self) -> Path:
        return self._ensure(self.assets_dir / "fonts")

    @property
    def templates_dir(self) -> Path:
        return self._ensure(self.assets_dir / "templates")


settings = Settings()
