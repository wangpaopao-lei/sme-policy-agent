"""元数据提取器测试"""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.metadata.regex_extractor import (
    extract_metadata_by_regex,
    get_missing_fields,
    _normalize_date,
    _extract_policy_number,
    _extract_publish_date,
    _extract_effective_date,
    _extract_issuing_authority,
    _extract_applicable_region,
    _classify_category,
)
from src.ingestion.metadata.llm_extractor import extract_metadata_by_llm


# ============================================================
# 正则提取器测试
# ============================================================


class TestNormalizeDate:
    def test_standard_date(self):
        assert _normalize_date("2024年3月15日") == "2024-03-15"

    def test_date_with_spaces(self):
        assert _normalize_date("2024 年 3 月 5 日") == "2024-03-05"

    def test_two_digit_month_day(self):
        assert _normalize_date("2024年12月31日") == "2024-12-31"

    def test_invalid_date(self):
        assert _normalize_date("不是日期") is None


class TestExtractPolicyNumber:
    def test_standard_format(self):
        text = "工信部联企业〔2024〕1号\n正文内容"
        assert _extract_policy_number(text) == "工信部联企业〔2024〕1号"

    def test_bracket_format(self):
        text = "财金[2026]15号\n正文"
        assert _extract_policy_number(text) == "财金[2026]15号"

    def test_no_policy_number(self):
        text = "这是一段没有文号的文本"
        assert _extract_policy_number(text) is None


class TestExtractIssuingAuthority:
    def test_from_policy_number(self):
        text = "正文"
        assert _extract_issuing_authority(text, "工信部联企业〔2024〕1号") == "工信部"

    def test_from_text(self):
        text = "财政部关于实施中小微企业贷款贴息政策的通知"
        assert _extract_issuing_authority(text, None) == "财政部"

    def test_from_publish_source(self):
        text = "发布来源:科技部\n正文内容"
        assert _extract_issuing_authority(text, None) == "科技部"


class TestExtractPublishDate:
    def test_date_at_end(self):
        text = "正文内容" * 100 + "\n2024年3月15日"
        assert _extract_publish_date(text) == "2024-03-15"

    def test_date_at_beginning(self):
        text = "2024年3月15日\n正文内容"
        assert _extract_publish_date(text) == "2024-03-15"

    def test_no_date(self):
        text = "没有任何日期的文本内容"
        assert _extract_publish_date(text) is None


class TestExtractEffectiveDate:
    def test_standard_pattern(self):
        text = "本办法自2024年4月1日起施行"
        assert _extract_effective_date(text) == "2024-04-01"

    def test_execute_pattern(self):
        text = "自2024年1月1日起执行"
        assert _extract_effective_date(text) == "2024-01-01"

    def test_no_effective_date(self):
        text = "没有生效日期"
        assert _extract_effective_date(text) is None


class TestExtractApplicableRegion:
    def test_national(self):
        text = "各省、自治区、直辖市人民政府：\n正文"
        assert _extract_applicable_region(text) == "全国"

    def test_no_region(self):
        text = "本办法适用于中小企业"
        assert _extract_applicable_region(text) is None


class TestClassifyCategory:
    def test_finance(self):
        assert _classify_category("关于实施贷款贴息政策") == "融资支持"

    def test_tax(self):
        assert _classify_category("关于税收优惠减免政策") == "税收优惠"

    def test_talent(self):
        assert _classify_category("关于人才培训就业政策") == "人才政策"

    def test_industry(self):
        assert _classify_category("关于推动工业互联网产业发展") == "产业扶持"

    def test_tech(self):
        assert _classify_category("关于支持科技创新研发") == "科技创新"


class TestExtractMetadataByRegex:
    def test_full_extraction(self):
        text = (
            "财金〔2026〕15号\n"
            "关于实施中小微企业贷款贴息政策的通知\n"
            "各省、自治区、直辖市财政厅：\n"
            "正文内容，涉及贷款贴息融资支持。\n"
            "本通知自2026年4月1日起施行。\n"
            "有效期至2027年12月31日。\n"
            "财政部\n2026年3月15日\n"
        )
        meta = extract_metadata_by_regex(text)
        assert meta["policy_number"] == "财金〔2026〕15号"
        assert meta["issuing_authority"] == "财政部"
        assert meta["publish_date"] == "2026-03-15"
        assert meta["effective_date"] == "2026-04-01"
        assert meta["expiry_date"] == "2027-12-31"
        assert meta["applicable_region"] == "全国"
        assert meta["category"] == "融资支持"

    def test_missing_fields(self):
        meta = {"title": "测试", "policy_number": None, "publish_date": "2024-01-01"}
        missing = get_missing_fields(meta)
        assert "policy_number" in missing
        assert "title" not in missing
        assert "publish_date" not in missing


class TestExtractOnRealData:
    @pytest.mark.skipif(
        not os.path.exists("data/关于实施中小微企业贷款贴息政策的通知.txt"),
        reason="测试数据文件不存在",
    )
    def test_real_policy_txt(self):
        with open("data/关于实施中小微企业贷款贴息政策的通知.txt") as f:
            text = f.read()
        meta = extract_metadata_by_regex(text)
        assert meta["category"] == "融资支持"
        assert meta["applicable_region"] == "全国"
        assert meta["publish_date"] is not None


# ============================================================
# LLM 提取器测试（使用 mock）
# ============================================================


class TestLlmExtractor:
    def test_extract_with_mock(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='{"policy_number": "财金〔2026〕15号", "effective_date": "2026-04-01"}')
        ]
        mock_client.messages.create.return_value = mock_response

        result = extract_metadata_by_llm(
            text="测试文本",
            missing_fields=["policy_number", "effective_date"],
            client=mock_client,
        )

        assert result["policy_number"] == "财金〔2026〕15号"
        assert result["effective_date"] == "2026-04-01"

    def test_only_returns_missing_fields(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='{"policy_number": "X号", "title": "不应返回的字段"}')
        ]
        mock_client.messages.create.return_value = mock_response

        result = extract_metadata_by_llm(
            text="测试文本",
            missing_fields=["policy_number"],
            client=mock_client,
        )

        assert "policy_number" in result
        assert "title" not in result

    def test_handles_json_in_code_block(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='```json\n{"policy_number": "X〔2024〕1号"}\n```')
        ]
        mock_client.messages.create.return_value = mock_response

        result = extract_metadata_by_llm(
            text="测试文本",
            missing_fields=["policy_number"],
            client=mock_client,
        )

        assert result["policy_number"] == "X〔2024〕1号"

    def test_handles_invalid_json(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="这不是JSON")]
        mock_client.messages.create.return_value = mock_response

        result = extract_metadata_by_llm(
            text="测试文本",
            missing_fields=["policy_number"],
            client=mock_client,
        )

        assert result == {}

    def test_empty_missing_fields(self):
        result = extract_metadata_by_llm(text="测试", missing_fields=[])
        assert result == {}

    def test_null_values_filtered(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='{"policy_number": null, "publish_date": "2024-01-01"}')
        ]
        mock_client.messages.create.return_value = mock_response

        result = extract_metadata_by_llm(
            text="测试文本",
            missing_fields=["policy_number", "publish_date"],
            client=mock_client,
        )

        assert "policy_number" not in result
        assert result["publish_date"] == "2024-01-01"
