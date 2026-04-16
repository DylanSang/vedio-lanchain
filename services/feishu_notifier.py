"""飞书消息通知 — 向飞书群发送工作流各阶段进度卡片消息."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

from config import settings
from models.schemas import (
    ContentPlan,
    EditedVideoResult,
    HotspotAnalysis,
    PublishResult,
    VideoResult,
)

logger = logging.getLogger(__name__)


def _build_client() -> lark.Client:
    return lark.Client.builder().app_id(settings.feishu.app_id).app_secret(settings.feishu.app_secret).build()


def send_text(chat_id: str, text: str) -> None:
    """发送纯文本消息到飞书群."""
    client = _build_client()
    body = CreateMessageRequestBody.builder() \
        .receive_id(chat_id) \
        .msg_type("text") \
        .content(json.dumps({"text": text})) \
        .build()
    req = CreateMessageRequest.builder().receive_id_type("chat_id").request_body(body).build()
    resp = client.im.v1.message.create(req)
    if not resp.success():
        logger.error("飞书消息发送失败: %s %s", resp.code, resp.msg)


def _send_interactive(chat_id: str, card: dict) -> None:
    """发送交互式卡片消息到飞书群."""
    client = _build_client()
    body = CreateMessageRequestBody.builder() \
        .receive_id(chat_id) \
        .msg_type("interactive") \
        .content(json.dumps(card)) \
        .build()
    req = CreateMessageRequest.builder().receive_id_type("chat_id").request_body(body).build()
    resp = client.im.v1.message.create(req)
    if not resp.success():
        logger.error("飞书卡片发送失败: %s %s", resp.code, resp.msg)


# ── 各阶段通知 ──


def notify_analyzing(chat_id: str, topic: str, workflow_id: str) -> None:
    """通知正在进行爆点分析."""
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "🔍 专家爆点分析中"},
            "template": "blue",
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**主题**: {topic}"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**工作流ID**: `{workflow_id}`"}},
            {"tag": "div", "text": {
                "tag": "lark_md",
                "content": "**状态**: 专家团队正在从用户心理、审美、创造性等维度分析主题爆点...",
            }},
        ],
    }
    _send_interactive(chat_id, card)


def notify_hotspot_result(chat_id: str, analysis: HotspotAnalysis, workflow_id: str) -> None:
    """通知爆点分析结果，无爆点时展示推荐主题并请求确认."""
    if analysis.has_hotspot:
        hotspots_text = "\n".join(
            f"  🔥 **{h.angle}** (潜力:{h.virality_score}/10)\n    {h.description}"
            for h in analysis.hotspots
        )
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "🔥 爆点分析完成 — 主题有爆发潜力"},
                "template": "green",
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**主题**: {analysis.topic}"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**综合评分**: {analysis.overall_score}/10"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**爆点**:\n{hotspots_text}"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**心理洞察**: {analysis.psychology_insight}"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**审美判断**: {analysis.aesthetic_insight}"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**创意空间**: {analysis.creativity_insight}"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": "**状态**: 爆点确认，开始生成内容方案..."}},
            ],
        }
    else:
        recs = "\n".join(
            f"  {i+1}. **{t}**" for i, t in enumerate(analysis.recommended_topics)
        )
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "⚠️ 爆点分析完成 — 主题爆发力不足"},
                "template": "orange",
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**主题**: {analysis.topic}"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**综合评分**: {analysis.overall_score}/10 (低于6分)"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**分析**: {analysis.summary}"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**推荐替代主题**:\n{recs}"}},
                {"tag": "hr"},
                {"tag": "div", "text": {
                    "tag": "lark_md",
                    "content": (
                        "请回复选择:\n"
                        f"- 回复 `#确认 {workflow_id}` 继续使用当前主题\n"
                        f"- 回复 `#换主题 {workflow_id} 新主题名称` 更换主题\n"
                        f"- 回复 `#推荐N {workflow_id}` 选择推荐的第N个主题 (如 `#推荐1 {workflow_id}`)"
                    ),
                }},
            ],
        }
    _send_interactive(chat_id, card)


def notify_editing_start(chat_id: str, count: int) -> None:
    """通知开始剪辑处理."""
    send_text(chat_id, f"✂️ 资深剪辑师开始处理 {count} 个视频...\n评估维度: 元素比例/流畅度/合理程度/创造性/审美/网感/镜头语言/色彩处理")


def notify_editing_done(chat_id: str, edited: list[EditedVideoResult]) -> None:
    """通知剪辑处理完成，展示评估摘要."""
    lines: list[str] = []
    for ev in edited:
        if ev.evaluation:
            dims = " | ".join(
                f"{d.name}:{d.score}" for d in ev.evaluation.dimensions
            )
            lines.append(
                f"  **[{ev.perspective}]** 综合:{ev.evaluation.overall_score}/10\n"
                f"    {dims}\n"
                f"    💡 {ev.evaluation.summary}"
            )
        else:
            lines.append(f"  **[{ev.perspective}]** (无评估数据)")

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "✂️ 资深剪辑处理完成"},
            "template": "green",
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}},
            {"tag": "div", "text": {"tag": "lark_md", "content": "**状态**: 剪辑完成，进入品牌标识/封面/适配/合规/发布..."}},
        ],
    }
    _send_interactive(chat_id, card)


def notify_workflow_start(chat_id: str, topic: str, workflow_id: str) -> None:
    """通知工作流已启动."""
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "🎬 视频工作流启动"},
            "template": "blue",
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**主题**: {topic}"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**工作流ID**: `{workflow_id}`"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": "**状态**: 正在生成内容方案..."}},
        ],
    }
    _send_interactive(chat_id, card)


def notify_plan_ready(chat_id: str, plan: ContentPlan, plan_files: list[Path]) -> None:
    """通知内容方案已生成."""
    variants_text = "\n".join(
        f"  {i+1}. **{v.perspective}** - {v.title} ({len(v.scenes)}个分镜)"
        for i, v in enumerate(plan.variants)
    )
    files_text = "\n".join(f"  - `{f.name}`" for f in plan_files)

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "📋 内容方案已生成"},
            "template": "green",
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**主题**: {plan.topic}"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**视角变体**:\n{variants_text}"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**方案文件**:\n{files_text}"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": "**状态**: 正在批量生成视频..."}},
        ],
    }
    _send_interactive(chat_id, card)


def notify_video_progress(chat_id: str, completed: int, total: int, latest: VideoResult) -> None:
    """通知视频生成进度."""
    send_text(
        chat_id,
        f"🎥 视频生成进度: {completed}/{total}\n"
        f"  最新完成: [{latest.perspective}] {latest.video_path}",
    )


def notify_videos_done(chat_id: str, videos: list[VideoResult]) -> None:
    """通知所有视频生成完成."""
    videos_text = "\n".join(
        f"  {i+1}. [{v.perspective}] {v.engine.value} - {v.duration:.0f}s"
        for i, v in enumerate(videos)
    )
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "🎥 视频批量生成完成"},
            "template": "green",
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**生成结果**:\n{videos_text}"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": "**状态**: 进入后期制作 (TTS配音/BGM/字幕/剪辑)..."}},
        ],
    }
    _send_interactive(chat_id, card)


def notify_publish_done(chat_id: str, results: list[PublishResult], topic: str) -> None:
    """通知全部发布完成，汇总所有结果."""
    success = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    lines: list[str] = []
    if success:
        lines.append("**发布成功**:")
        for r in success:
            lines.append(f"  ✅ {r.platform.value}: {r.url}")
    if failed:
        lines.append("**发布失败**:")
        for r in failed:
            lines.append(f"  ❌ {r.platform.value}: {r.error}")

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "📢 视频发布完成"},
            "template": "green" if not failed else "orange",
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**主题**: {topic}"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"✅ 成功 {len(success)} / ❌ 失败 {len(failed)} / 共 {len(results)}",
                },
            },
        ],
    }
    _send_interactive(chat_id, card)


def notify_error(chat_id: str, workflow_id: str, error: str) -> None:
    """通知工作流异常."""
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "❗ 工作流异常"},
            "template": "red",
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**工作流ID**: `{workflow_id}`"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**错误**: {error}"}},
        ],
    }
    _send_interactive(chat_id, card)
