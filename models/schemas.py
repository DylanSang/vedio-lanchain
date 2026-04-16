from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Platform(str, Enum):
    DOUYIN = "douyin"
    BILIBILI = "bilibili"
    XIAOHONGSHU = "xiaohongshu"
    KUAISHOU = "kuaishou"
    WECHAT_VIDEO = "wechat_video"


class VideoEngine(str, Enum):
    JIMENG = "jimeng"
    XIAOYUNQUE = "xiaoyunque"


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    WAITING_CONFIRMATION = "waiting_confirmation"
    PLANNING = "planning"
    GENERATING = "generating"
    POST_PRODUCING = "post_producing"
    EDITING = "editing"
    BRANDING = "branding"
    ADAPTING = "adapting"
    COMPLIANCE_CHECK = "compliance_check"
    SCHEDULING = "scheduling"
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    FAILED = "failed"


# ── 飞书消息解析结果 ──


class FeishuCommand(BaseModel):
    topic: str
    variant_count: int = 3
    platforms: list[Platform] = Field(default_factory=lambda: list(Platform))
    style: Optional[str] = None
    engine: VideoEngine = VideoEngine.JIMENG
    chat_id: str = ""
    message_id: str = ""


# ── 爆点分析 ──


class Hotspot(BaseModel):
    """单个爆点."""
    angle: str
    description: str
    virality_score: int = Field(ge=1, le=10, description="爆点潜力 1-10")
    target_audience: str = ""


class HotspotAnalysis(BaseModel):
    """专家+创意师对主题的爆点分析结果."""
    topic: str
    has_hotspot: bool
    overall_score: int = Field(ge=1, le=10, description="主题整体爆点潜力 1-10")
    hotspots: list[Hotspot] = Field(default_factory=list)
    psychology_insight: str = ""
    aesthetic_insight: str = ""
    creativity_insight: str = ""
    recommended_topics: list[str] = Field(
        default_factory=list,
        description="当无爆点时推荐的替代主题",
    )
    summary: str = ""


# ── 内容方案 ──


class SceneScript(BaseModel):
    scene_id: int
    prompt: str
    duration: float = 5.0
    narration: str = ""


class ContentVariant(BaseModel):
    variant_id: int
    perspective: str
    title: str
    description: str
    scenes: list[SceneScript]
    tags: list[str] = Field(default_factory=list)
    target_platforms: list[Platform] = Field(default_factory=list)


class ContentPlan(BaseModel):
    topic: str
    variants: list[ContentVariant]
    created_at: datetime = Field(default_factory=datetime.now)


# ── 视频生成结果 ──


class VideoResult(BaseModel):
    variant_id: int
    perspective: str
    video_path: str
    engine: VideoEngine
    duration: float = 0.0


# ── 剪辑评估与处理 ──


class EditingDimension(BaseModel):
    """单个剪辑评估维度."""
    name: str
    score: int = Field(ge=1, le=10)
    comment: str = ""
    suggestion: str = ""


class EditingEvaluation(BaseModel):
    """资深剪辑师对视频的综合评估."""
    variant_id: int
    overall_score: int = Field(ge=1, le=10)
    dimensions: list[EditingDimension] = Field(default_factory=list)
    editing_instructions: list[str] = Field(
        default_factory=list,
        description="具体的 FFmpeg 剪辑指令描述",
    )
    ffmpeg_filters: str = Field(default="", description="FFmpeg 滤镜链参数")
    summary: str = ""


class EditedVideoResult(BaseModel):
    """剪辑处理后的视频结果."""
    variant_id: int
    perspective: str
    original_path: str
    edited_path: str
    evaluation: Optional[EditingEvaluation] = None
    engine: VideoEngine = VideoEngine.JIMENG
    duration: float = 0.0


# ── 平台发布结果 ──


class PublishResult(BaseModel):
    platform: Platform
    success: bool
    url: str = ""
    error: str = ""
    variant_id: int = 0


# ── 工作流状态 ──


class WorkflowState(BaseModel):
    workflow_id: str
    topic: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    command: Optional[FeishuCommand] = None
    hotspot_analysis: Optional[HotspotAnalysis] = None
    plan: Optional[ContentPlan] = None
    videos: list[VideoResult] = Field(default_factory=list)
    edited_videos: list[EditedVideoResult] = Field(default_factory=list)
    publish_results: list[PublishResult] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    error: str = ""
