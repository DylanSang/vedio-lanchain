"""飞书 Bot 入口 — 通过 lark-oapi WebSocket 长连接监听群消息并启动工作流."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass, field

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1, P2ImMessageReceiveV1Data

from config import settings
from models.schemas import FeishuCommand, Platform, VideoEngine

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── 消息解析 ──

_PLATFORM_MAP: dict[str, Platform] = {
    "抖音": Platform.DOUYIN,
    "douyin": Platform.DOUYIN,
    "b站": Platform.BILIBILI,
    "bilibili": Platform.BILIBILI,
    "小红书": Platform.XIAOHONGSHU,
    "快手": Platform.KUAISHOU,
    "kuaishou": Platform.KUAISHOU,
    "微信视频号": Platform.WECHAT_VIDEO,
    "视频号": Platform.WECHAT_VIDEO,
}

_CMD_PATTERN = re.compile(
    r"#视频\s+"
    r"(?P<topic>[^\[【]+?)\s*"
    r"(?:\[视角数[:：]?\s*(?P<variants>\d+)\])?\s*"
    r"(?:\[平台[:：]?\s*(?P<platforms>[^\]]+)\])?\s*"
    r"(?:\[风格[:：]?\s*(?P<style>[^\]]+)\])?\s*"
    r"(?:\[引擎[:：]?\s*(?P<engine>[^\]]+)\])?\s*$",
    re.DOTALL,
)


def parse_command(text: str) -> FeishuCommand | None:
    """解析飞书消息文本为 FeishuCommand; 不匹配返回 None."""
    text = text.strip()
    m = _CMD_PATTERN.match(text)
    if not m:
        return None

    topic = m.group("topic").strip()
    variant_count = int(m.group("variants") or settings.default_variant_count)

    platforms: list[Platform] = []
    if m.group("platforms"):
        for name in re.split(r"[,，、\s]+", m.group("platforms")):
            name = name.strip().lower()
            if name in _PLATFORM_MAP:
                platforms.append(_PLATFORM_MAP[name])
    if not platforms:
        platforms = list(Platform)

    style = (m.group("style") or "").strip() or None

    engine = VideoEngine.JIMENG
    if m.group("engine"):
        eng_raw = m.group("engine").strip().lower()
        if "小云雀" in eng_raw or "xiaoyunque" in eng_raw:
            engine = VideoEngine.XIAOYUNQUE

    return FeishuCommand(
        topic=topic,
        variant_count=variant_count,
        platforms=platforms,
        style=style,
        engine=engine,
    )


# ── 用户确认/换主题 指令解析 ──

_CONFIRM_PATTERN = re.compile(r"#确认\s+(?P<wid>\w+)", re.DOTALL)
_CHANGE_TOPIC_PATTERN = re.compile(r"#换主题\s+(?P<wid>\w+)\s+(?P<new_topic>.+)", re.DOTALL)
_RECOMMEND_PATTERN = re.compile(r"#推荐(?P<idx>\d+)\s+(?P<wid>\w+)", re.DOTALL)


@dataclass
class UserConfirmation:
    """用户对爆点分析的回复."""
    workflow_id: str
    action: str  # "confirm" | "change" | "recommend"
    new_topic: str = ""
    recommend_index: int = 0


def parse_confirmation(text: str) -> UserConfirmation | None:
    """解析用户确认/换主题消息."""
    text = text.strip()

    m = _CONFIRM_PATTERN.match(text)
    if m:
        return UserConfirmation(workflow_id=m.group("wid"), action="confirm")

    m = _CHANGE_TOPIC_PATTERN.match(text)
    if m:
        return UserConfirmation(
            workflow_id=m.group("wid"),
            action="change",
            new_topic=m.group("new_topic").strip(),
        )

    m = _RECOMMEND_PATTERN.match(text)
    if m:
        return UserConfirmation(
            workflow_id=m.group("wid"),
            action="recommend",
            recommend_index=int(m.group("idx")),
        )

    return None


# 等待用户确认的工作流注册表: workflow_id -> asyncio.Future
_pending_confirmations: dict[str, asyncio.Future[UserConfirmation]] = {}


def register_pending_confirmation(workflow_id: str) -> asyncio.Future[UserConfirmation]:
    """注册一个等待用户确认的 Future."""
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[UserConfirmation] = loop.create_future()
    _pending_confirmations[workflow_id] = fut
    return fut


def resolve_confirmation(confirmation: UserConfirmation) -> bool:
    """解析用户确认消息，完成对应的 Future."""
    fut = _pending_confirmations.pop(confirmation.workflow_id, None)
    if fut is None or fut.done():
        return False
    fut.set_result(confirmation)
    return True


# ── 消息事件处理 ──


def _extract_text(content_json: str) -> str:
    """从飞书消息 content JSON 中提取纯文本."""
    try:
        data = json.loads(content_json)
        return data.get("text", "")
    except (json.JSONDecodeError, TypeError):
        return content_json


def _on_message(data: P2ImMessageReceiveV1) -> None:
    """处理收到的飞书消息事件."""
    event = data.event
    if event is None or event.message is None:
        return

    msg = event.message
    text = _extract_text(msg.content)
    logger.info("收到消息: %s", text)

    # 先检查是否为用户确认/换主题消息
    confirmation = parse_confirmation(text)
    if confirmation is not None:
        resolved = resolve_confirmation(confirmation)
        if resolved:
            logger.info("用户确认已处理: wid=%s action=%s", confirmation.workflow_id, confirmation.action)
        else:
            logger.warning("未找到等待确认的工作流: %s", confirmation.workflow_id)
        return

    # 再检查是否为新的视频指令
    cmd = parse_command(text)
    if cmd is None:
        logger.debug("非视频指令，跳过: %s", text)
        return

    cmd.chat_id = msg.chat_id or ""
    cmd.message_id = msg.message_id or ""
    logger.info("解析指令: topic=%s variants=%d platforms=%s", cmd.topic, cmd.variant_count, cmd.platforms)

    from services.orchestrator import run_workflow

    workflow_id = uuid.uuid4().hex[:12]
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(run_workflow(workflow_id, cmd))
    except RuntimeError:
        asyncio.ensure_future(run_workflow(workflow_id, cmd))


# ── 启动 Bot ──


def create_bot() -> lark.ws.Client:
    """创建并返回飞书 WebSocket 长连接客户端."""
    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(_on_message)
        .build()
    )

    client = lark.ws.Client(
        settings.feishu.app_id,
        settings.feishu.app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
    )
    return client


def main() -> None:
    logger.info("启动飞书 Bot (WebSocket 长连接) ...")
    bot = create_bot()
    bot.start()


if __name__ == "__main__":
    main()
