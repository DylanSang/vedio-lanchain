"""LangChain Orchestrator — 串联全流程的工作流编排.

完整流程 (17 步):
  飞书指令
    -> Step 1: 专家+创意师爆点分析
    -> Step 1.5: (无爆点时) 推荐替代主题 -> 等待用户确认
    -> Step 2: 内容方案生成 (基于爆点方向)
    -> Step 3: 方案导出 .md + 素材库索引
    -> Step 4: 视频批量生成 (含缓存检查)
    -> Step 5: TTS 配音生成
    -> Step 6: BGM 匹配
    -> Step 7: 音频处理链 (TTS+BGM动态ducking → 归一化 → 合成到视频)
    -> Step 8: 字幕生成 + 烧录
    -> Step 9: 资深剪辑师评估 + FFmpeg 后处理
    -> Step 10: 品牌标识 (片头片尾+水印)
    -> Step 11: 封面图生成
    -> Step 12: 多尺寸视频适配
    -> Step 13: 平台文案适配
    -> Step 14: 内容合规审查 (阻断违规)
    -> Step 15: 定时发布调度 / 多平台发布 (多账号+重试+草稿箱)
    -> Step 16: 飞书回报
    -> Step 17: 数据回收调度
"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from models.database import save_workflow
from models.schemas import (
    ContentPlan,
    ContentVariant,
    EditedVideoResult,
    FeishuCommand,
    HotspotAnalysis,
    Platform,
    PublishResult,
    VideoResult,
    WorkflowState,
    WorkflowStatus,
)
from services.account_manager import AccountManager
from services.asset_library import AssetLibrary
from services.audio_mixer import run_audio_pipeline
from services.bgm_matcher import select_bgm
from services.brand_overlay import apply_brand_identity
from services.compliance_checker import run_compliance_check
from services.content_planner import generate_content_plan
from services.copy_adapter import adapt_copy_batch
from services.feishu_notifier import (
    notify_analyzing,
    notify_editing_done,
    notify_editing_start,
    notify_error,
    notify_hotspot_result,
    notify_plan_ready,
    notify_publish_done,
    notify_videos_done,
    notify_workflow_start,
    send_text,
)
from services.plan_exporter import export_plan
from services.publish_scheduler import get_publish_schedule, schedule_publish
from services.publisher import VideoMetadata, get_publisher
from services.retry_handler import retry_with_backoff, save_to_drafts
from services.subtitle_generator import burn_subtitles, generate_ass
from services.thumbnail_generator import generate_thumbnail
from services.topic_analyst import analyze_topic_hotspot
from services.tts_service import generate_tts_for_scenes
from services.video_adapter import adapt_video_batch
from services.video_editor import edit_videos_batch
from services.video_generator import generate_videos_batch

logger = logging.getLogger(__name__)

_CONFIRMATION_TIMEOUT = 600

_asset_lib = AssetLibrary()
_account_mgr = AccountManager()

# 追踪已调度但尚未完成的发布任务 {workflow_id: tracker_dict}
_scheduled_workflows: dict[str, dict] = {}


def _safe_name(text: str, max_len: int = 20) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", text)[:max_len].strip("_")


async def run_workflow(workflow_id: str, command: FeishuCommand) -> WorkflowState:
    """执行完整 17 步工作流."""
    state = WorkflowState(workflow_id=workflow_id, topic=command.topic, command=command)
    save_workflow(state)
    chat_id = command.chat_id

    try:
        # ── Step 1: 专家+创意师爆点分析 ──
        state.status = WorkflowStatus.ANALYZING
        save_workflow(state)
        if chat_id:
            notify_analyzing(chat_id, command.topic, workflow_id)

        analysis = await analyze_topic_hotspot(
            topic=command.topic,
            platforms=[p.value for p in command.platforms],
            style=command.style or "",
        )
        state.hotspot_analysis = analysis
        save_workflow(state)
        if chat_id:
            notify_hotspot_result(chat_id, analysis, workflow_id)

        # ── Step 1.5: 无爆点时等待用户确认 ──
        final_topic = command.topic
        if not analysis.has_hotspot:
            final_topic = await _wait_for_topic_confirmation(workflow_id, command, analysis, state)
            command.topic = final_topic
            state.topic = final_topic
            state.command = command
            save_workflow(state)

        # ── Step 2: 内容方案生成 ──
        state.status = WorkflowStatus.PLANNING
        save_workflow(state)
        if chat_id:
            notify_workflow_start(chat_id, final_topic, workflow_id)

        hotspot_hints = _build_hotspot_hints(analysis)
        if hotspot_hints and not command.style:
            command.style = hotspot_hints
        elif hotspot_hints:
            command.style = f"{command.style}; 爆点方向: {hotspot_hints}"

        plan = await generate_content_plan(command)
        state.plan = plan
        save_workflow(state)

        # ── Step 3: 方案导出 .md + 素材库索引 ──
        plan_files = export_plan(plan)
        for pf in plan_files:
            tags = plan.variants[0].tags if plan.variants else []
            _asset_lib.index_plan(final_topic, str(pf), tags)
        if chat_id:
            notify_plan_ready(chat_id, plan, plan_files)

        # ── Step 4: 视频批量生成 (含缓存检查) ──
        state.status = WorkflowStatus.GENERATING
        save_workflow(state)

        videos = await _generate_with_cache(plan, final_topic, command)
        state.videos = videos
        save_workflow(state)
        if chat_id:
            notify_videos_done(chat_id, videos)

        # ── Step 5-8: 后期制作 (TTS + BGM + 动态ducking混音 + 字幕) ──
        state.status = WorkflowStatus.POST_PRODUCING
        save_workflow(state)
        if chat_id:
            send_text(chat_id, "🎙 开始后期制作: TTS配音 → BGM动态ducking → 混音 → 字幕 ...")

        post_produced_videos: list[EditedVideoResult] = []
        for video, variant in zip(videos, plan.variants):
            prefix = _safe_name(f"{final_topic}_{variant.perspective}")
            result = await _post_produce_variant(video, variant, prefix)
            post_produced_videos.append(result)

        # ── Step 9: 资深剪辑师评估 ──
        state.status = WorkflowStatus.EDITING
        save_workflow(state)
        if chat_id:
            notify_editing_start(chat_id, len(post_produced_videos))

        edited_videos = await edit_videos_batch(
            videos=[
                VideoResult(
                    variant_id=v.variant_id,
                    perspective=v.perspective,
                    video_path=v.edited_path,
                    engine=v.engine,
                    duration=v.duration,
                )
                for v in post_produced_videos
            ],
            variants=plan.variants,
        )
        state.edited_videos = edited_videos
        save_workflow(state)
        if chat_id:
            notify_editing_done(chat_id, edited_videos)

        # ── Step 10: 品牌标识 ──
        state.status = WorkflowStatus.BRANDING
        save_workflow(state)
        if chat_id:
            send_text(chat_id, "📌 添加品牌标识: 片头 + 水印 + 片尾 ...")
        from config import settings
        for ev in edited_videos:
            prefix = _safe_name(f"{final_topic}_{ev.perspective}")
            branded = apply_brand_identity(
                Path(ev.edited_path), settings.videos_dir, prefix,
            )
            ev.edited_path = str(branded)

        # ── Step 11: 封面图生成 ──
        if chat_id:
            send_text(chat_id, "🖼 生成封面图 ...")
        cover_paths: dict[int, dict[Platform, Path]] = {}
        for ev in edited_videos:
            variant = _find_variant(plan, ev.variant_id)
            if not variant:
                continue
            platforms = variant.target_platforms or command.platforms
            covers: dict[Platform, Path] = {}
            for p in platforms:
                covers[p] = await generate_thumbnail(
                    Path(ev.edited_path), variant.title,
                    final_topic, variant.perspective, p,
                )
            cover_paths[ev.variant_id] = covers

        # ── Step 12: 多尺寸视频适配 ──
        state.status = WorkflowStatus.ADAPTING
        save_workflow(state)
        if chat_id:
            send_text(chat_id, "📐 多尺寸视频适配 ...")
        adapted_paths: dict[int, dict[Platform, Path]] = {}
        for ev in edited_videos:
            variant = _find_variant(plan, ev.variant_id)
            if not variant:
                continue
            platforms = variant.target_platforms or command.platforms
            prefix = _safe_name(f"{final_topic}_{ev.perspective}")
            adapted = adapt_video_batch(
                Path(ev.edited_path), platforms, settings.videos_dir, prefix,
            )
            adapted_paths[ev.variant_id] = adapted

        # ── Step 13: 平台文案适配 ──
        if chat_id:
            send_text(chat_id, "✍ 平台文案适配 ...")
        copy_map: dict[int, dict[Platform, VideoMetadata]] = {}
        for ev in edited_videos:
            variant = _find_variant(plan, ev.variant_id)
            if not variant:
                continue
            platforms = variant.target_platforms or command.platforms
            adapted_copies = await adapt_copy_batch(
                variant.title, variant.description, variant.tags,
                final_topic, platforms,
            )
            copy_map[ev.variant_id] = adapted_copies

        # ── Step 14: 内容合规审查 (阻断违规) ──
        state.status = WorkflowStatus.COMPLIANCE_CHECK
        save_workflow(state)
        if chat_id:
            send_text(chat_id, "🛡 内容合规审查 ...")
        blocked_pairs: set[tuple[int, Platform]] = set()
        compliance_warnings: list[str] = []
        for ev in edited_videos:
            variant = _find_variant(plan, ev.variant_id)
            if not variant:
                continue
            platforms = variant.target_platforms or command.platforms
            for p in platforms:
                meta = copy_map.get(ev.variant_id, {}).get(p)
                if not meta:
                    continue
                check = run_compliance_check(meta.title, meta.description, meta.tags, p)
                if not check.passed:
                    blocked_pairs.add((ev.variant_id, p))
                    for issue in check.issues:
                        if issue.severity == "error":
                            compliance_warnings.append(
                                f"[{ev.perspective}/{p.value}] {issue.message}"
                            )

        if compliance_warnings and chat_id:
            blocked_msg = "\n".join(compliance_warnings[:10])
            send_text(
                chat_id,
                f"⛔ 合规审查拦截 {len(blocked_pairs)} 个发布任务:\n{blocked_msg}\n"
                f"已自动跳过违规平台发布。",
            )

        # ── 缓存视频到素材库 (视频已就绪, 不依赖发布时间) ──
        for ev in edited_videos:
            _asset_lib.cache_video(final_topic, ev.variant_id, ev.edited_path)

        # ── Step 15: 定时发布调度 ──
        state.status = WorkflowStatus.SCHEDULING
        save_workflow(state)

        schedule_preview = get_publish_schedule(command.platforms)
        if chat_id:
            sched_lines = [
                f"  {p.value}: {t.strftime('%m-%d %H:%M')}"
                for p, t in schedule_preview.items()
            ]
            send_text(chat_id, "⏰ 各平台黄金发布时间:\n" + "\n".join(sched_lines))

        job_count, blocked_results = _schedule_all_publishes(
            edited_videos, plan, command.platforms,
            adapted_paths, copy_map, cover_paths, workflow_id,
            blocked_pairs, chat_id, state,
        )

        if job_count == 0:
            # 全部被拦截或无目标平台, 直接完成
            state.publish_results = blocked_results
            state.status = WorkflowStatus.COMPLETED
            save_workflow(state)
            if chat_id:
                notify_publish_done(chat_id, blocked_results, final_topic)
            logger.info("[%s] 无可调度发布任务, 工作流完成", workflow_id)
        else:
            # Step 16: 工作流标记为「已调度」, 实际发布由 APScheduler 回调执行
            state.status = WorkflowStatus.SCHEDULED
            save_workflow(state)
            if chat_id:
                send_text(
                    chat_id,
                    f"📅 已调度 {job_count} 个发布任务, 将在黄金时间自动发布\n"
                    f"发布完成后将通过飞书通知结果",
                )
            logger.info("[%s] 已调度 %d 个定时发布任务", workflow_id, job_count)
        # Step 17 (数据回收) 由 _on_all_publishes_done 在全部发布完成后触发

    except Exception as e:
        logger.exception("[%s] 工作流异常: %s", workflow_id, e)
        state.status = WorkflowStatus.FAILED
        state.error = str(e)
        save_workflow(state)
        if chat_id:
            notify_error(chat_id, workflow_id, str(e))

    return state


# ── 辅助函数 ──


async def _generate_with_cache(
    plan: ContentPlan, topic: str, command: FeishuCommand,
) -> list[VideoResult]:
    """生成视频, 优先检查素材库缓存."""
    cached: list[VideoResult] = []
    to_generate: list[ContentVariant] = []

    for variant in plan.variants:
        hit = _asset_lib.get_cached_video(topic, variant.variant_id)
        if hit:
            logger.info("缓存命中: %s variant_%d", topic, variant.variant_id)
            cached.append(VideoResult(
                variant_id=variant.variant_id,
                perspective=variant.perspective,
                video_path=hit,
                engine=command.engine,
            ))
        else:
            to_generate.append(variant)

    if to_generate:
        new_videos = await generate_videos_batch(
            variants=to_generate,
            topic=topic,
            engine=command.engine,
            style=command.style or "",
        )
        cached.extend(new_videos)

    return sorted(cached, key=lambda v: v.variant_id)


async def _post_produce_variant(
    video: VideoResult,
    variant: ContentVariant,
    prefix: str,
) -> EditedVideoResult:
    """对单个变体执行后期制作: TTS → BGM → 动态ducking混音 → 字幕."""
    from config import settings

    video_path = Path(video.video_path)
    scenes = [
        {"scene_id": s.scene_id, "narration": s.narration, "duration": s.duration}
        for s in variant.scenes
    ]

    tts_segments = await generate_tts_for_scenes(scenes, variant.title, variant.perspective)
    bgm_path = await select_bgm(variant.title, variant.description, variant.perspective)

    audio_dir = settings.audio_dir
    with_audio = await run_audio_pipeline(
        tts_segments, bgm_path, video_path, audio_dir, prefix,
    )

    sub_path = audio_dir / f"{prefix}.ass"
    generate_ass(tts_segments, sub_path)
    final_path = settings.videos_dir / f"{prefix}_subtitled.mp4"
    try:
        burn_subtitles(with_audio, sub_path, final_path)
    except RuntimeError:
        final_path = with_audio

    return EditedVideoResult(
        variant_id=video.variant_id,
        perspective=video.perspective,
        original_path=video.video_path,
        edited_path=str(final_path),
        engine=video.engine,
        duration=video.duration,
    )


def _schedule_all_publishes(
    edited_videos: list[EditedVideoResult],
    plan: ContentPlan,
    default_platforms: list[Platform],
    adapted_paths: dict[int, dict[Platform, Path]],
    copy_map: dict[int, dict[Platform, VideoMetadata]],
    cover_paths: dict[int, dict[Platform, Path]],
    workflow_id: str,
    blocked_pairs: set[tuple[int, Platform]],
    chat_id: str,
    state: WorkflowState,
) -> tuple[int, list[PublishResult]]:
    """将所有发布任务加入 APScheduler 定时队列.

    Returns:
        (已调度任务数, 被合规拦截的结果列表)
    """
    variant_map = {v.variant_id: v for v in plan.variants}
    job_count = 0
    blocked_results: list[PublishResult] = []

    for video in edited_videos:
        variant = variant_map.get(video.variant_id)
        if not variant:
            continue

        platforms = variant.target_platforms or default_platforms
        for platform in platforms:
            if (video.variant_id, platform) in blocked_pairs:
                blocked_results.append(PublishResult(
                    platform=platform, success=False,
                    error="合规审查拦截: 内容不符合平台规则",
                    variant_id=video.variant_id,
                ))
                continue

            vid_path = adapted_paths.get(video.variant_id, {}).get(platform) or Path(video.edited_path)
            meta = copy_map.get(video.variant_id, {}).get(platform) or VideoMetadata(
                title=variant.title, description=variant.description, tags=variant.tags,
            )
            cover = cover_paths.get(video.variant_id, {}).get(platform)

            job_id = f"pub_{workflow_id}_{video.variant_id}_{platform.value}"
            publish_time = schedule_publish(
                platform=platform,
                publish_fn=_scheduled_publish_callback,
                job_id=job_id,
                workflow_id=workflow_id,
                variant_id=video.variant_id,
                perspective=video.perspective,
                platform_value=platform.value,
                video_path=str(vid_path),
                meta_title=meta.title,
                meta_description=meta.description,
                meta_tags=meta.tags,
                cover_path=str(cover) if cover else "",
                chat_id=chat_id,
            )
            logger.info(
                "[%s] variant_%d -> %s 定时 %s",
                workflow_id, video.variant_id, platform.value,
                publish_time.strftime("%m-%d %H:%M"),
            )
            job_count += 1

    if job_count > 0:
        _scheduled_workflows[workflow_id] = {
            "total": job_count,
            "completed": 0,
            "results": list(blocked_results),
            "state": state,
            "edited_videos": edited_videos,
            "chat_id": chat_id,
        }

    return job_count, blocked_results


async def _scheduled_publish_callback(
    workflow_id: str,
    variant_id: int,
    perspective: str,
    platform_value: str,
    video_path: str,
    meta_title: str,
    meta_description: str,
    meta_tags: list[str],
    cover_path: str,
    chat_id: str,
) -> None:
    """由 APScheduler 在黄金时间触发的单平台发布回调."""
    platform = Platform(platform_value)
    publisher = get_publisher(platform)
    meta = VideoMetadata(title=meta_title, description=meta_description, tags=meta_tags)
    if cover_path:
        meta.cover_path = cover_path

    account = _account_mgr.select_account(platform, meta.title, meta.description)
    if account:
        logger.info("定时发布使用账号 [%s] %s", platform.value, account.name)

    result = PublishResult(platform=platform, success=False, variant_id=variant_id)
    try:
        result = await retry_with_backoff(
            publisher.publish, Path(video_path), meta,
            max_retries=2, task_name=f"scheduled_{platform.value}_{variant_id}",
        )
        result.variant_id = variant_id
    except Exception as e:
        save_to_drafts(
            workflow_id, variant_id, platform.value, video_path,
            {"title": meta.title, "description": meta.description, "tags": meta.tags},
            str(e),
        )
        result = PublishResult(
            platform=platform, success=False, error=str(e), variant_id=variant_id,
        )
    finally:
        await publisher.close()

    if chat_id:
        icon = "✅" if result.success else "❌"
        url_part = f"\n🔗 {result.url}" if result.url else ""
        err_part = f"\n原因: {result.error}" if result.error else ""
        send_text(
            chat_id,
            f"{icon} 定时发布 [{platform.value}] {perspective}{url_part}{err_part}",
        )

    tracker = _scheduled_workflows.get(workflow_id)
    if not tracker:
        logger.warning("[%s] 找不到调度追踪器, 发布结果可能丢失", workflow_id)
        return

    tracker["results"].append(result)
    tracker["completed"] += 1
    logger.info(
        "[%s] 定时发布进度 %d/%d",
        workflow_id, tracker["completed"], tracker["total"],
    )

    if tracker["completed"] >= tracker["total"]:
        _on_all_publishes_done(workflow_id)


def _on_all_publishes_done(workflow_id: str) -> None:
    """所有定时发布完成后: 飞书汇总通知 + 数据回收调度 + 标记完成."""
    tracker = _scheduled_workflows.pop(workflow_id, None)
    if not tracker:
        return

    state: WorkflowState = tracker["state"]
    results: list[PublishResult] = tracker["results"]
    state.publish_results = results

    chat_id = tracker.get("chat_id", "")
    if chat_id:
        notify_publish_done(chat_id, results, state.topic)

    _schedule_data_collection(workflow_id, results, tracker["edited_videos"])

    state.status = WorkflowStatus.COMPLETED
    save_workflow(state)
    logger.info("[%s] 所有定时发布完成, 工作流已完成", workflow_id)


def _schedule_data_collection(
    workflow_id: str,
    results: list[PublishResult],
    videos: list[EditedVideoResult],
) -> None:
    """调度发布后的数据回收任务 (24h/48h/7d)."""
    try:
        from services.analytics_collector import collect_platform_data
        from services.publish_scheduler import get_scheduler

        scheduler = get_scheduler()
        from datetime import datetime, timedelta
        from apscheduler.triggers.date import DateTrigger

        for r in results:
            if not r.success:
                continue
            vid = next((v for v in videos if v.variant_id == r.variant_id), None)
            variant_id = vid.variant_id if vid else 0

            for period, delta in [("24h", 24), ("48h", 48), ("7d", 168)]:
                scheduler.add_job(
                    collect_platform_data,
                    trigger=DateTrigger(run_date=datetime.now() + timedelta(hours=delta)),
                    id=f"analytics_{workflow_id}_{r.platform.value}_{variant_id}_{period}",
                    kwargs={
                        "platform": r.platform,
                        "publish_url": r.url,
                        "workflow_id": workflow_id,
                        "variant_id": variant_id,
                        "period": period,
                    },
                    replace_existing=True,
                )
        logger.info("[%s] 数据回收已调度: %d 个任务", workflow_id, len([r for r in results if r.success]) * 3)
    except Exception as e:
        logger.warning("数据回收调度失败 (非致命): %s", e)


async def _wait_for_topic_confirmation(
    workflow_id: str,
    command: FeishuCommand,
    analysis: HotspotAnalysis,
    state: WorkflowState,
) -> str:
    """等待用户对爆点分析结果的确认/换主题回复."""
    from bot import register_pending_confirmation, UserConfirmation

    state.status = WorkflowStatus.WAITING_CONFIRMATION
    save_workflow(state)

    fut = register_pending_confirmation(workflow_id)
    try:
        confirmation: UserConfirmation = await asyncio.wait_for(fut, timeout=_CONFIRMATION_TIMEOUT)
    except asyncio.TimeoutError:
        logger.info("[%s] 用户确认超时, 使用原始主题继续", workflow_id)
        return command.topic

    if confirmation.action == "confirm":
        return command.topic
    if confirmation.action == "change":
        return confirmation.new_topic
    if confirmation.action == "recommend":
        idx = confirmation.recommend_index - 1
        if 0 <= idx < len(analysis.recommended_topics):
            return analysis.recommended_topics[idx]

    return command.topic


def _build_hotspot_hints(analysis: HotspotAnalysis) -> str:
    if not analysis.hotspots:
        return ""
    return "; ".join(f"{h.angle}({h.description[:30]})" for h in analysis.hotspots[:3])


def _find_variant(plan: ContentPlan, variant_id: int) -> ContentVariant | None:
    return next((v for v in plan.variants if v.variant_id == variant_id), None)
