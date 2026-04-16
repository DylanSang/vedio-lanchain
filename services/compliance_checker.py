"""内容合规审查 — 敏感词检测 + 平台规则校验 + AI 内容标注.

发布前的安全门禁, 避免违规导致限流/封号。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from models.schemas import Platform

logger = logging.getLogger(__name__)

# 基础敏感词库 (实际使用时应大幅扩充)
_SENSITIVE_WORDS = [
    "赌博", "色情", "暴力", "毒品", "枪支",
    "政治敏感", "分裂", "邪教",
    "假药", "传销", "诈骗",
]

# 各平台专属禁忌规则
_PLATFORM_RULES: dict[Platform, list[dict]] = {
    Platform.DOUYIN: [
        {"pattern": r"微信|wx|weixin|v信", "message": "抖音禁止引流到微信"},
        {"pattern": r"竞品logo", "message": "抖音禁止展示竞品logo"},
    ],
    Platform.XIAOHONGSHU: [
        {"pattern": r"微信号|wx\d|加我微信", "message": "小红书禁止留微信号"},
        {"pattern": r"二维码", "message": "小红书禁止引流二维码"},
    ],
    Platform.BILIBILI: [
        {"pattern": r"抖音水印|快手水印", "message": "B站禁止其他平台水印"},
    ],
}


@dataclass
class ComplianceIssue:
    """单个合规问题."""
    severity: str  # "error" | "warning"
    category: str
    message: str
    location: str = ""


@dataclass
class ComplianceResult:
    """合规审查结果."""
    passed: bool = True
    issues: list[ComplianceIssue] = field(default_factory=list)
    ai_label_required: bool = True

    def add_issue(self, severity: str, category: str, message: str, location: str = "") -> None:
        self.issues.append(ComplianceIssue(severity=severity, category=category,
                                            message=message, location=location))
        if severity == "error":
            self.passed = False


def check_sensitive_words(text: str) -> list[str]:
    """检查文本中的敏感词."""
    found = []
    text_lower = text.lower()
    for word in _SENSITIVE_WORDS:
        if word in text_lower:
            found.append(word)
    return found


def check_platform_rules(text: str, platform: Platform) -> list[dict]:
    """检查平台专属规则."""
    rules = _PLATFORM_RULES.get(platform, [])
    violations = []
    for rule in rules:
        if re.search(rule["pattern"], text, re.IGNORECASE):
            violations.append(rule)
    return violations


def run_compliance_check(
    title: str,
    description: str,
    tags: list[str],
    platform: Platform,
) -> ComplianceResult:
    """对视频元数据执行完整合规审查.

    Returns:
        审查结果, passed=False 表示不建议发布
    """
    result = ComplianceResult()
    full_text = f"{title} {description} {' '.join(tags)}"

    # 敏感词
    sensitive = check_sensitive_words(full_text)
    for word in sensitive:
        result.add_issue("error", "敏感词", f"检测到敏感词: {word}", "文案")

    # 平台规则
    violations = check_platform_rules(full_text, platform)
    for v in violations:
        result.add_issue("error", "平台规则", v["message"], platform.value)

    # AI 内容标注提醒
    result.ai_label_required = True
    result.add_issue("warning", "AI标注", "建议标注'AI生成内容' (部分平台强制要求)")

    if result.passed:
        logger.info("合规审查通过 [%s]: %s", platform.value, title[:30])
    else:
        logger.warning("合规审查未通过 [%s]: %d 个问题", platform.value, len(result.issues))

    return result
