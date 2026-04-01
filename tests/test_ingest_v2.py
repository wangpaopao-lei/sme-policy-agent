"""v2 摄入脚本测试（mock 所有重依赖）"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest


# 因为 ingest_v2.py 的重依赖（Embedder 等）在函数内部 import，
# 需要 patch 它们的源模块
PATCH_PREFIX = {
    "run_pipeline": "src.ingestion.pipeline_v2.run_pipeline",
    "create_parent_child_chunks": "src.chunking.parent_child.create_parent_child_chunks",
    "Embedder": "src.retrieval.embedder.Embedder",
    "VectorStore": "src.retrieval.vector_store.VectorStore",
    "BM25Store": "src.retrieval.bm25_store.BM25Store",
}


def _make_doc(source="a.txt", tables=None):
    return {
        "final_document": "# 标题\n内容",
        "metadata": {"source": source, "category": "融资支持"},
        "tables": tables or [],
        "source": source,
    }


def _make_pipeline_result(documents):
    return {
        "total_files": len(documents),
        "processed": len(documents),
        "failed": [],
        "documents": documents,
    }


class TestIngestV2:
    @patch(PATCH_PREFIX["BM25Store"])
    @patch(PATCH_PREFIX["VectorStore"])
    @patch(PATCH_PREFIX["Embedder"])
    @patch(PATCH_PREFIX["create_parent_child_chunks"])
    @patch(PATCH_PREFIX["run_pipeline"])
    def test_full_pipeline_flow(
        self, mock_pipeline, mock_chunk, mock_embedder_cls, mock_vs_cls, mock_bm25_cls
    ):
        """验证完整流程的编排顺序"""
        mock_pipeline.return_value = _make_pipeline_result([_make_doc()])
        mock_chunk.return_value = (
            [{"id": "p1", "text": "父chunk", "metadata": {"source": "a.txt", "role": "parent"}}],
            [{"id": "c1", "text": "子chunk", "metadata": {"source": "a.txt", "role": "child"}}],
        )
        mock_embedder = mock_embedder_cls.return_value
        mock_embedder.embed_batch.return_value = [[0.1] * 768]
        mock_vs = mock_vs_cls.return_value
        mock_vs.count.return_value = 2
        mock_bm25 = mock_bm25_cls.return_value
        mock_bm25.count.return_value = 1

        from scripts.ingest_v2 import ingest
        ingest(use_llm=False, clean=False)

        mock_pipeline.assert_called_once()
        mock_chunk.assert_called_once()
        mock_embedder.embed_batch.assert_called_once_with(["子chunk"])
        mock_vs.add_chunks_without_embeddings.assert_called_once()
        mock_vs.add_chunks.assert_called_once()
        mock_bm25.build_index.assert_called_once()
        mock_bm25.save.assert_called_once()

    @patch(PATCH_PREFIX["BM25Store"])
    @patch(PATCH_PREFIX["VectorStore"])
    @patch(PATCH_PREFIX["Embedder"])
    @patch(PATCH_PREFIX["create_parent_child_chunks"])
    @patch(PATCH_PREFIX["run_pipeline"])
    def test_clean_clears_vector_store(
        self, mock_pipeline, mock_chunk, mock_embedder_cls, mock_vs_cls, mock_bm25_cls
    ):
        mock_pipeline.return_value = _make_pipeline_result([_make_doc()])
        mock_chunk.return_value = (
            [{"id": "p1", "text": "父", "metadata": {"role": "parent"}}],
            [{"id": "c1", "text": "子", "metadata": {"role": "child"}}],
        )
        mock_embedder_cls.return_value.embed_batch.return_value = [[0.1] * 768]
        mock_vs = mock_vs_cls.return_value
        mock_vs.count.return_value = 2
        mock_bm25_cls.return_value.count.return_value = 1

        from scripts.ingest_v2 import ingest
        ingest(use_llm=False, clean=True)

        mock_vs.clear.assert_called_once()

    @patch(PATCH_PREFIX["run_pipeline"])
    def test_no_documents_exits_early(self, mock_pipeline):
        mock_pipeline.return_value = _make_pipeline_result([])

        from scripts.ingest_v2 import ingest
        ingest(use_llm=False)
        # 不应崩溃

    @patch(PATCH_PREFIX["BM25Store"])
    @patch(PATCH_PREFIX["VectorStore"])
    @patch(PATCH_PREFIX["Embedder"])
    @patch(PATCH_PREFIX["create_parent_child_chunks"])
    @patch(PATCH_PREFIX["run_pipeline"])
    def test_table_keywords_injected(
        self, mock_pipeline, mock_chunk, mock_embedder_cls, mock_vs_cls, mock_bm25_cls
    ):
        """表格加权关键词应注入到 BM25"""
        mock_pipeline.return_value = _make_pipeline_result([_make_doc(
            tables=[{
                "markdown": "| 列1 | 列2 |\n| --- | --- |",
                "keywords": {"贷款贴息": 5, "中小企业": 3},
            }],
        )])
        mock_chunk.return_value = (
            [{"id": "p1", "text": "父chunk", "metadata": {"source": "a.txt", "role": "parent"}}],
            [{
                "id": "c1",
                "text": "| 列1 | 列2 |\n| --- | --- |\n其他内容",
                "metadata": {"source": "a.txt", "role": "child"},
            }],
        )
        mock_embedder_cls.return_value.embed_batch.return_value = [[0.1] * 768]
        mock_vs_cls.return_value.count.return_value = 2
        mock_bm25 = mock_bm25_cls.return_value
        mock_bm25.count.return_value = 1

        from scripts.ingest_v2 import ingest
        ingest(use_llm=False)

        mock_bm25.add_weighted_keywords.assert_called_once_with(
            "c1", {"贷款贴息": 5, "中小企业": 3}
        )
