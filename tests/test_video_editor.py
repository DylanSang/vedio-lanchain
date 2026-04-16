"""资深剪辑师模块单测."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from models.schemas import ContentVariant, EditingEvaluation, Platform, SceneScript

_MOCK_VARIANT = ContentVariant(
    variant_id=1,
    perspective="科普讲解",
    title="3分钟看懂AI发展",
    description="科普视角解读",
    scenes=[
        SceneScript(scene_id=1, prompt="Futuristic AI lab", duration=5.0, narration="欢迎来到AI世界"),
        SceneScript(scene_id=2, prompt="Robot assembly line", duration=6.0, narration="机器人正在改变制造业"),
    ],
    tags=["AI", "科技"],
    target_platforms=[Platform.DOUYIN],
)

_MOCK_EVALUATION_RESULT = {
    "variant_id": 1,
    "overall_score": 7,
    "dimensions": [
        {"name": "元素比例", "score": 7, "comment": "主体占比合理", "suggestion": "可增加文字注释"},
        {"name": "流畅度", "score": 8, "comment": "转场自然", "suggestion": "可加交叉溶解"},
        {"name": "合理程度", "score": 7, "comment": "画面与旁白匹配", "suggestion": "无"},
        {"name": "创造性", "score": 6, "comment": "表达较常规", "suggestion": "可加数据可视化"},
        {"name": "审美", "score": 8, "comment": "科技感强", "suggestion": "保持"},
        {"name": "网感", "score": 7, "comment": "符合抖音调性", "suggestion": "可加热门BGM"},
        {"name": "镜头语言", "score": 6, "comment": "景别单一", "suggestion": "增加特写镜头"},
        {"name": "色彩处理", "score": 7, "comment": "偏冷色调", "suggestion": "微调饱和度"},
    ],
    "editing_instructions": [
        "增加片头0.5秒淡入",
        "调高整体饱和度10%",
        "微增对比度",
    ],
    "ffmpeg_filters": "eq=brightness=0.03:contrast=1.1:saturation=1.15,unsharp=5:5:0.5",
    "summary": "整体质量良好，微调色彩和锐度即可",
}


@pytest.mark.asyncio
async def test_evaluate_video():
    """测试剪辑师评估返回正确结构."""
    with patch("services.video_editor._build_chain") as mock_chain:
        mock_runnable = AsyncMock()
        mock_runnable.ainvoke.return_value = _MOCK_EVALUATION_RESULT
        mock_chain.return_value = mock_runnable

        from services.video_editor import evaluate_video

        result = await evaluate_video(_MOCK_VARIANT)

        assert isinstance(result, EditingEvaluation)
        assert result.overall_score == 7
        assert len(result.dimensions) == 8
        assert result.dimensions[0].name == "元素比例"
        assert result.ffmpeg_filters != ""
        assert "eq=" in result.ffmpeg_filters


def test_sanitize_filter():
    """测试 FFmpeg 滤镜安全过滤."""
    from services.video_editor import _sanitize_filter

    assert _sanitize_filter("eq=brightness=0.05") == "eq=brightness=0.05"
    assert _sanitize_filter("malicious; rm -rf /") == "malicious rm -rf /"
    assert _sanitize_filter("") == ""
    assert _sanitize_filter("   ") == ""
