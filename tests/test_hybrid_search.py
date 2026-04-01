"""混合检索测试"""

from unittest.mock import MagicMock

import pytest

from src.retrieval.hybrid_searcher import rrf_merge, resolve_parents, HybridSearcher


# ============================================================
# RRF 融合测试
# ============================================================


class TestRRFMerge:
    def test_basic_merge(self):
        vector = [
            {"id": "a", "text": "A", "score": 0.9, "metadata": {}},
            {"id": "c", "text": "C", "score": 0.7, "metadata": {}},
        ]
        bm25 = [
            {"id": "b", "text": "B", "score": 10, "metadata": {}},
            {"id": "a", "text": "A", "score": 8, "metadata": {}},
        ]
        result = rrf_merge(vector, bm25, top_k=3)

        # a 出现在两个列表中，RRF 分数应最高
        assert result[0]["id"] == "a"
        assert len(result) == 3

    def test_rrf_scores_present(self):
        vector = [{"id": "a", "text": "A", "score": 0.9, "metadata": {}}]
        bm25 = [{"id": "b", "text": "B", "score": 10, "metadata": {}}]
        result = rrf_merge(vector, bm25)

        for r in result:
            assert "rrf_score" in r
            assert r["rrf_score"] > 0

    def test_respects_top_k(self):
        vector = [{"id": f"v{i}", "text": f"V{i}", "score": 0.9 - i*0.1, "metadata": {}} for i in range(10)]
        bm25 = [{"id": f"b{i}", "text": f"B{i}", "score": 10 - i, "metadata": {}} for i in range(10)]
        result = rrf_merge(vector, bm25, top_k=5)
        assert len(result) == 5

    def test_empty_inputs(self):
        assert rrf_merge([], []) == []
        result = rrf_merge([{"id": "a", "text": "A", "score": 0.9, "metadata": {}}], [])
        assert len(result) == 1

    def test_duplicate_in_both(self):
        """同一文档在两路中都出现时，分数叠加"""
        vector = [{"id": "a", "text": "A", "score": 0.9, "metadata": {}}]
        bm25 = [{"id": "a", "text": "A", "score": 10, "metadata": {}}]
        result = rrf_merge(vector, bm25)
        # 单个文档的 RRF 分数应 > 任一路单独的分数
        single_score = 1 / (60 + 1)
        assert result[0]["rrf_score"] > single_score


# ============================================================
# 父 chunk 展开测试
# ============================================================


class TestResolveParents:
    def test_basic_resolve(self):
        children = [
            {"id": "c1", "text": "child1", "rrf_score": 0.5, "metadata": {"parent_id": "p1", "role": "child"}},
            {"id": "c2", "text": "child2", "rrf_score": 0.3, "metadata": {"parent_id": "p2", "role": "child"}},
        ]

        mock_store = MagicMock()
        mock_store.get_by_ids.return_value = [
            {"id": "p1", "text": "parent1 full text", "metadata": {"role": "parent"}},
            {"id": "p2", "text": "parent2 full text", "metadata": {"role": "parent"}},
        ]

        result = resolve_parents(children, mock_store)

        assert len(result) == 2
        assert result[0]["id"] == "p1"  # p1 的 rrf_score 更高
        assert result[0]["text"] == "parent1 full text"
        mock_store.get_by_ids.assert_called_once_with(["p1", "p2"])

    def test_dedup_parents(self):
        """多个子 chunk 指向同一父 chunk 时去重"""
        children = [
            {"id": "c1", "text": "child1", "rrf_score": 0.5, "metadata": {"parent_id": "p1"}},
            {"id": "c2", "text": "child2", "rrf_score": 0.3, "metadata": {"parent_id": "p1"}},
        ]

        mock_store = MagicMock()
        mock_store.get_by_ids.return_value = [
            {"id": "p1", "text": "parent1", "metadata": {}},
        ]

        result = resolve_parents(children, mock_store)
        assert len(result) == 1
        mock_store.get_by_ids.assert_called_once_with(["p1"])

    def test_no_parent_id(self):
        """没有 parent_id 时返回原始结果"""
        children = [{"id": "c1", "text": "text", "metadata": {}}]

        mock_store = MagicMock()
        result = resolve_parents(children, mock_store)
        assert result == children


# ============================================================
# HybridSearcher 集成测试（mock 依赖）
# ============================================================


class TestHybridSearcher:
    def _make_searcher(self):
        mock_vector = MagicMock()
        mock_bm25 = MagicMock()
        mock_embedder = MagicMock()
        mock_embedder.embed.return_value = [0.1] * 768

        searcher = HybridSearcher(
            vector_store=mock_vector,
            bm25_store=mock_bm25,
            embedder=mock_embedder,
        )
        return searcher, mock_vector, mock_bm25, mock_embedder

    def test_search_calls_both(self):
        searcher, mock_vector, mock_bm25, mock_embedder = self._make_searcher()

        mock_vector.query.return_value = [
            {"id": "c1", "text": "向量结果", "score": 0.9, "metadata": {"parent_id": "p1", "role": "child"}},
        ]
        mock_bm25.search.return_value = [
            {"id": "c1", "text": "BM25结果", "score": 10, "metadata": {"parent_id": "p1", "role": "child"}},
        ]
        mock_vector.get_by_ids.return_value = [
            {"id": "p1", "text": "父chunk", "metadata": {"role": "parent"}},
        ]

        results = searcher.search("测试查询", top_k=5)

        mock_embedder.embed.assert_called_once_with("测试查询")
        mock_vector.query.assert_called_once()
        mock_bm25.search.assert_called_once_with("测试查询", top_k=20)
        assert len(results) > 0

    def test_search_with_filters(self):
        searcher, mock_vector, mock_bm25, _ = self._make_searcher()
        mock_vector.query.return_value = []
        mock_bm25.search.return_value = []

        searcher.search("测试", filters={"category": "融资支持"})

        # 验证 where 条件被传给 vector_store
        call_kwargs = mock_vector.query.call_args[1]
        where = call_kwargs["where"]
        assert where is not None

    def test_search_no_expand(self):
        searcher, mock_vector, mock_bm25, _ = self._make_searcher()

        mock_vector.query.return_value = [
            {"id": "c1", "text": "结果", "score": 0.9, "metadata": {"role": "child"}},
        ]
        mock_bm25.search.return_value = []

        results = searcher.search("测试", expand_parents=False)

        # 不应调用 get_by_ids
        mock_vector.get_by_ids.assert_not_called()
        assert len(results) > 0

    def test_search_with_reranker(self):
        searcher, mock_vector, mock_bm25, _ = self._make_searcher()
        mock_reranker = MagicMock()
        searcher.reranker = mock_reranker

        mock_vector.query.return_value = [
            {"id": "c1", "text": "结果1", "score": 0.9, "metadata": {"parent_id": "p1", "role": "child"}},
            {"id": "c2", "text": "结果2", "score": 0.7, "metadata": {"parent_id": "p2", "role": "child"}},
        ]
        mock_bm25.search.return_value = []
        mock_reranker.rerank.return_value = [
            {"id": "c2", "text": "结果2", "rrf_score": 0.5, "metadata": {"parent_id": "p2", "role": "child"}},
        ]
        mock_vector.get_by_ids.return_value = [
            {"id": "p2", "text": "父2", "metadata": {}},
        ]

        results = searcher.search("测试", top_k=1, use_rerank=True)

        mock_reranker.rerank.assert_called_once()
