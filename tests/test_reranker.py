"""Reranker 测试

由于 CrossEncoder 模型加载重且依赖 PyTorch，这里用 mock 测试。
集成测试（真实模型）标记为 integration。
"""

from unittest.mock import MagicMock

import pytest

from src.retrieval.reranker import Reranker


class TestReranker:
    def _make_reranker(self):
        """构造 mock reranker（不加载真实模型）"""
        reranker = Reranker.__new__(Reranker)
        reranker.model = MagicMock()
        return reranker

    def test_rerank_basic(self):
        reranker = self._make_reranker()
        reranker.model.predict.return_value = [0.3, 0.9, 0.1]

        candidates = [
            {"id": "a", "text": "文档A", "rrf_score": 0.5},
            {"id": "b", "text": "文档B", "rrf_score": 0.4},
            {"id": "c", "text": "文档C", "rrf_score": 0.3},
        ]

        results = reranker.rerank("查询", candidates, top_k=2)

        assert len(results) == 2
        assert results[0]["id"] == "b"  # 分数 0.9 最高
        assert results[1]["id"] == "a"  # 分数 0.3
        assert results[0]["rerank_score"] == 0.9

    def test_rerank_preserves_fields(self):
        reranker = self._make_reranker()
        reranker.model.predict.return_value = [0.8]

        candidates = [
            {"id": "a", "text": "内容", "rrf_score": 0.5, "metadata": {"source": "x.pdf"}},
        ]

        results = reranker.rerank("查询", candidates)

        assert results[0]["metadata"]["source"] == "x.pdf"
        assert results[0]["rrf_score"] == 0.5
        assert "rerank_score" in results[0]

    def test_rerank_empty_candidates(self):
        reranker = self._make_reranker()
        results = reranker.rerank("查询", [])
        assert results == []

    def test_rerank_respects_top_k(self):
        reranker = self._make_reranker()
        reranker.model.predict.return_value = [0.5, 0.3, 0.9, 0.1, 0.7]

        candidates = [{"id": str(i), "text": f"文档{i}"} for i in range(5)]

        results = reranker.rerank("查询", candidates, top_k=3)
        assert len(results) == 3
        # 应该是分数最高的3个
        assert results[0]["rerank_score"] == 0.9

    def test_rerank_does_not_modify_original(self):
        reranker = self._make_reranker()
        reranker.model.predict.return_value = [0.5]

        original = {"id": "a", "text": "内容"}
        candidates = [original]

        results = reranker.rerank("查询", candidates)

        # 原始对象不应被修改
        assert "rerank_score" not in original
        assert "rerank_score" in results[0]

    def test_predict_called_with_pairs(self):
        reranker = self._make_reranker()
        reranker.model.predict.return_value = [0.5, 0.3]

        candidates = [
            {"id": "a", "text": "文档A"},
            {"id": "b", "text": "文档B"},
        ]

        reranker.rerank("测试查询", candidates)

        reranker.model.predict.assert_called_once_with([
            ("测试查询", "文档A"),
            ("测试查询", "文档B"),
        ])
