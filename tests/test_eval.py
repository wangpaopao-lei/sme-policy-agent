"""评估模块测试"""

import json
from unittest.mock import MagicMock

import pytest

from evaluation.retrieval_eval import recall_at_k, mrr, evaluate_retrieval, _normalize_source, _source_match
from evaluation.answer_eval import judge_answer


# ============================================================
# 引号归一化测试
# ============================================================


class TestNormalizeSource:
    def test_chinese_double_quotes(self):
        assert _normalize_source('\u201c测试\u201d.pdf') == '"测试".pdf'

    def test_chinese_single_quotes(self):
        assert _normalize_source('\u2018测试\u2019.pdf') == "'测试'.pdf"

    def test_fullwidth_space(self):
        assert _normalize_source('测试\u3000文件.pdf') == '测试 文件.pdf'

    def test_source_match_different_quotes(self):
        """全角引号和 ASCII 引号应匹配"""
        assert _source_match('\u201c人工智能\u201d.pdf', '"人工智能".pdf')
        assert _source_match('"人工智能".pdf', '\u201c人工智能\u201d.pdf')

    def test_source_match_identical(self):
        assert _source_match('test.pdf', 'test.pdf')

    def test_source_match_different(self):
        assert not _source_match('a.pdf', 'b.pdf')


# ============================================================
# 检索评估测试
# ============================================================


class TestRecallAtK:
    def test_hit_at_first(self):
        assert recall_at_k(["a.pdf", "b.pdf"], ["a.pdf"]) == 1.0

    def test_hit_at_last(self):
        assert recall_at_k(["a.pdf", "b.pdf", "c.pdf", "d.pdf", "e.pdf"], ["e.pdf"], k=5) == 1.0

    def test_miss(self):
        assert recall_at_k(["a.pdf", "b.pdf"], ["c.pdf"], k=5) == 0.0

    def test_no_expected(self):
        """无答案类问题"""
        assert recall_at_k(["a.pdf"], []) == 1.0

    def test_multiple_expected(self):
        """多个期望来源，命中任一即可"""
        assert recall_at_k(["a.pdf", "b.pdf"], ["c.pdf", "b.pdf"]) == 1.0

    def test_respects_k(self):
        assert recall_at_k(["a.pdf", "b.pdf", "c.pdf"], ["c.pdf"], k=2) == 0.0
        assert recall_at_k(["a.pdf", "b.pdf", "c.pdf"], ["c.pdf"], k=3) == 1.0

    def test_quote_normalization(self):
        """全角引号和 ASCII 引号应被视为匹配"""
        assert recall_at_k(
            ['\u201c人工智能\u201d.pdf'],
            ['"人工智能".pdf'],
        ) == 1.0


class TestMRR:
    def test_first_rank(self):
        assert mrr(["a.pdf", "b.pdf"], ["a.pdf"]) == 1.0

    def test_second_rank(self):
        assert mrr(["a.pdf", "b.pdf"], ["b.pdf"]) == 0.5

    def test_third_rank(self):
        assert mrr(["a.pdf", "b.pdf", "c.pdf"], ["c.pdf"]) == pytest.approx(1/3)

    def test_miss(self):
        assert mrr(["a.pdf"], ["z.pdf"]) == 0.0

    def test_no_expected(self):
        assert mrr(["a.pdf"], []) == 1.0

    def test_quote_normalization(self):
        assert mrr(['\u201c测试\u201d.pdf'], ['"测试".pdf']) == 1.0


class TestEvaluateRetrieval:
    def test_overall_scores(self):
        results = [
            {"question": "Q1", "expected_sources": ["a.pdf"], "retrieved_sources": ["a.pdf", "b.pdf"], "category": "简单事实"},
            {"question": "Q2", "expected_sources": ["c.pdf"], "retrieved_sources": ["b.pdf", "c.pdf"], "category": "简单事实"},
            {"question": "Q3", "expected_sources": ["d.pdf"], "retrieved_sources": ["x.pdf", "y.pdf"], "category": "跨文档"},
        ]
        report = evaluate_retrieval(results, k=5)

        assert report["overall"]["recall_at_k"] == pytest.approx(2/3)
        assert report["overall"]["total"] == 3

    def test_by_category(self):
        results = [
            {"question": "Q1", "expected_sources": ["a.pdf"], "retrieved_sources": ["a.pdf"], "category": "简单事实"},
            {"question": "Q2", "expected_sources": ["b.pdf"], "retrieved_sources": ["x.pdf"], "category": "跨文档"},
        ]
        report = evaluate_retrieval(results, k=5)

        assert report["by_category"]["简单事实"]["recall_at_k"] == 1.0
        assert report["by_category"]["跨文档"]["recall_at_k"] == 0.0

    def test_failures_collected(self):
        results = [
            {"question": "Q1", "expected_sources": ["a.pdf"], "retrieved_sources": ["x.pdf"], "category": "简单事实"},
        ]
        report = evaluate_retrieval(results, k=5)

        assert len(report["failures"]) == 1
        assert report["failures"][0]["question"] == "Q1"


# ============================================================
# LLM-as-Judge 测试（mock）
# ============================================================


class TestJudgeAnswer:
    def test_basic_judge(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text='{"faithfulness": 5, "relevance": 4, "completeness": 3, "correctness": 4, "reason": "回答基本准确"}'
        )]
        mock_client.messages.create.return_value = mock_response

        result = judge_answer(
            question="测试问题",
            answer="测试回答",
            context="测试上下文",
            expected_answer="期望答案",
            client=mock_client,
        )

        assert result["faithfulness"] == 5
        assert result["relevance"] == 4
        assert "reason" in result

    def test_invalid_json_returns_zeros(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="无法解析的内容")]
        mock_client.messages.create.return_value = mock_response

        result = judge_answer(
            question="Q", answer="A", context="C", expected_answer="E",
            client=mock_client,
        )

        assert result["faithfulness"] == 0
        assert "JSON 解析失败" in result["reason"]


# ============================================================
# 评估数据集验证
# ============================================================


class TestEvalDataset:
    def test_dataset_structure(self):
        with open("evaluation/dataset/eval_set.json", "r") as f:
            data = json.load(f)

        assert len(data) == 50

        required_fields = ["id", "question", "expected_answer", "expected_sources", "category"]
        for item in data:
            for field in required_fields:
                assert field in item, f"ID {item.get('id', '?')} 缺少字段 {field}"

    def test_dataset_categories(self):
        with open("evaluation/dataset/eval_set.json", "r") as f:
            data = json.load(f)

        valid_categories = {"简单事实", "多条件", "跨文档", "精确引用", "时间相关", "否定问题", "无答案", "模糊口语"}
        for item in data:
            assert item["category"] in valid_categories, f"ID {item['id']} 的类别 '{item['category']}' 无效"

    def test_ids_unique(self):
        with open("evaluation/dataset/eval_set.json", "r") as f:
            data = json.load(f)

        ids = [item["id"] for item in data]
        assert len(ids) == len(set(ids)), "存在重复 ID"
