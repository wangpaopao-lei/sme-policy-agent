"""表格处理器测试"""

from unittest.mock import MagicMock

import pytest

from src.ingestion.table.table_processor import (
    table_to_natural_language,
    generate_questions_and_keywords,
    process_table,
    process_tables,
    _extract_section_context,
)


# ============================================================
# 表格转自然语言测试
# ============================================================


class TestTableToNaturalLanguage:
    def test_multi_column_table(self):
        md = (
            "| 企业类型 | 贴息比例 | 最高额度 |\n"
            "| --- | --- | --- |\n"
            "| 小型企业 | 2% | 500万 |\n"
            "| 微型企业 | 2.5% | 200万 |"
        )
        result = table_to_natural_language(md)
        assert "企业类型为小型企业" in result
        assert "贴息比例为2%" in result
        assert "最高额度为500万" in result
        assert "企业类型为微型企业" in result

    def test_blockquote_table(self):
        """专栏类表格（引用块格式）直接返回清理后的文本"""
        md = "> 专栏 1 技术提升工程\n>\n> 1.重点方向一\n> 2.重点方向二"
        result = table_to_natural_language(md)
        assert "专栏 1 技术提升工程" in result
        assert "1.重点方向一" in result
        assert result.startswith("专栏")  # 不应该有 > 前缀

    def test_insufficient_rows(self):
        """不足3行的表格返回原文"""
        md = "| 标题 |\n| --- |"
        result = table_to_natural_language(md)
        assert result == md

    def test_empty_cells_handled(self):
        md = (
            "| 类型 | 比例 |\n"
            "| --- | --- |\n"
            "| 小型 |  |"
        )
        result = table_to_natural_language(md)
        assert "类型为小型" in result


# ============================================================
# 章节上下文提取测试
# ============================================================


class TestExtractSectionContext:
    def test_finds_nearest_heading(self):
        full_md = "# 标题\n\n## 第一章\n\n### 第三条 补贴标准\n\n| 类型 | 比例 |"
        table_md = "| 类型 | 比例 |"
        result = _extract_section_context(table_md, full_md)
        assert "第三条 补贴标准" in result

    def test_no_heading_found(self):
        full_md = "正文内容\n| 类型 | 比例 |"
        table_md = "| 类型 | 比例 |"
        result = _extract_section_context(table_md, full_md)
        assert result == ""

    def test_empty_full_markdown(self):
        result = _extract_section_context("| 表格 |", "")
        assert result == ""


# ============================================================
# LLM Q&K 生成测试（mock）
# ============================================================


def _make_mock_client(response_json: str) -> MagicMock:
    """构造 mock Anthropic 客户端"""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=response_json)]
    mock_client.messages.create.return_value = mock_response
    return mock_client


class TestGenerateQuestionsAndKeywords:
    def test_basic_generation(self):
        response = '{"questions": ["贴息比例是多少？"], "keywords": {"贴息": 5, "小型企业": 3}}'
        client = _make_mock_client(response)

        result = generate_questions_and_keywords(
            table_content="小型企业贴息比例为2%",
            title="贴息政策",
            client=client,
        )

        assert len(result["questions"]) == 1
        assert "贴息比例是多少？" in result["questions"]
        assert result["keywords"]["贴息"] == 5
        assert result["keywords"]["小型企业"] == 3

    def test_json_in_code_block(self):
        response = '```json\n{"questions": ["Q1"], "keywords": {"K1": 3}}\n```'
        client = _make_mock_client(response)

        result = generate_questions_and_keywords(
            table_content="测试内容",
            client=client,
        )

        assert result["questions"] == ["Q1"]

    def test_invalid_json_returns_empty(self):
        client = _make_mock_client("这不是JSON")

        result = generate_questions_and_keywords(
            table_content="测试内容",
            client=client,
        )

        assert result["questions"] == []
        assert result["keywords"] == {}

    def test_missing_fields_returns_defaults(self):
        response = '{"questions": ["Q1"]}'
        client = _make_mock_client(response)

        result = generate_questions_and_keywords(
            table_content="测试内容",
            client=client,
        )

        assert result["questions"] == ["Q1"]
        assert result["keywords"] == {}

    def test_prompt_includes_context(self):
        response = '{"questions": [], "keywords": {}}'
        client = _make_mock_client(response)

        generate_questions_and_keywords(
            table_content="表格内容",
            title="测试标题",
            section_context="第三条",
            client=client,
        )

        # 验证调用时 prompt 包含了标题和章节
        call_args = client.messages.create.call_args
        prompt = call_args[1]["messages"][0]["content"]
        assert "测试标题" in prompt
        assert "第三条" in prompt


# ============================================================
# process_table 集成测试（mock LLM）
# ============================================================


class TestProcessTable:
    def test_process_multi_column_table(self):
        table_md = (
            "| 企业类型 | 贴息比例 |\n"
            "| --- | --- |\n"
            "| 小型企业 | 2% |"
        )
        response = '{"questions": ["小型企业贴息比例？"], "keywords": {"贴息": 5}}'
        client = _make_mock_client(response)

        result = process_table(
            table_markdown=table_md,
            title="贴息通知",
            client=client,
        )

        assert result["markdown"] == table_md
        assert "企业类型为小型企业" in result["natural_language"]
        assert "小型企业贴息比例？" in result["questions"]
        assert result["keywords"]["贴息"] == 5

    def test_process_blockquote_table(self):
        table_md = "> 专栏 1 技术提升\n>\n> 1.方向一\n> 2.方向二"
        response = '{"questions": ["技术方向有哪些？"], "keywords": {"技术": 4}}'
        client = _make_mock_client(response)

        result = process_table(
            table_markdown=table_md,
            title="产业方案",
            client=client,
        )

        assert "专栏 1 技术提升" in result["natural_language"]
        assert ">" not in result["natural_language"]


class TestProcessTables:
    def test_batch_processing(self):
        tables = [
            {"markdown": "> 专栏1\n>\n> 内容1", "page": 5},
            {"markdown": "> 专栏2\n>\n> 内容2", "page": 6},
        ]
        response = '{"questions": ["Q"], "keywords": {"K": 3}}'
        client = _make_mock_client(response)

        results = process_tables(
            tables=tables,
            title="测试",
            client=client,
        )

        assert len(results) == 2
        assert results[0]["page"] == 5
        assert results[1]["page"] == 6
        # LLM 被调用了2次
        assert client.messages.create.call_count == 2

    def test_empty_tables(self):
        results = process_tables(tables=[], title="测试")
        assert results == []
