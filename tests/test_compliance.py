"""内容合规审查单元测试."""
from models.schemas import Platform
from services.compliance_checker import (
    check_sensitive_words,
    check_platform_rules,
    run_compliance_check,
)


class TestSensitiveWords:
    def test_detects_sensitive(self):
        found = check_sensitive_words("这里有赌博内容")
        assert "赌博" in found

    def test_clean_text(self):
        found = check_sensitive_words("今天天气不错")
        assert len(found) == 0


class TestPlatformRules:
    def test_douyin_wechat_violation(self):
        violations = check_platform_rules("加我微信号123", Platform.DOUYIN)
        assert len(violations) > 0

    def test_xiaohongshu_qrcode_violation(self):
        violations = check_platform_rules("扫二维码关注", Platform.XIAOHONGSHU)
        assert len(violations) > 0

    def test_bilibili_clean(self):
        violations = check_platform_rules("今天分享一个技巧", Platform.BILIBILI)
        assert len(violations) == 0


class TestFullComplianceCheck:
    def test_fails_on_sensitive(self):
        result = run_compliance_check("赌博攻略", "教你赌博", ["赌博"], Platform.DOUYIN)
        assert not result.passed

    def test_passes_clean_content(self):
        result = run_compliance_check("Python教程", "学习Python", ["编程"], Platform.BILIBILI)
        assert result.passed
        assert result.ai_label_required
