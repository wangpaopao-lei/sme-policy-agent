"""混合检索器

向量检索 + BM25 关键词检索 → RRF 融合 → 可选 Reranker 精排 → 父 chunk 展开。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.retrieval.vector_store import VectorStore
    from src.retrieval.bm25_store import BM25Store


def rrf_merge(
    vector_results: list[dict],
    bm25_results: list[dict],
    k: int = 60,
    top_k: int = 10,
) -> list[dict]:
    """
    Reciprocal Rank Fusion 融合两路检索结果。

    参数:
        vector_results: 向量检索结果 [{id, text, score, metadata}]
        bm25_results: BM25 检索结果 [{id, text, score, metadata}]
        k: RRF 参数（默认 60）
        top_k: 融合后返回数量

    返回: 融合后的结果列表（按 RRF 分数降序）
    """
    scores = {}
    doc_map = {}

    for rank, doc in enumerate(vector_results):
        doc_id = doc["id"]
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
        doc_map[doc_id] = doc

    for rank, doc in enumerate(bm25_results):
        doc_id = doc["id"]
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
        if doc_id not in doc_map:
            doc_map[doc_id] = doc

    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)[:top_k]

    results = []
    for doc_id in sorted_ids:
        doc = doc_map[doc_id].copy()
        doc["rrf_score"] = round(scores[doc_id], 6)
        results.append(doc)

    return results


def resolve_parents(
    child_results: list[dict],
    vector_store: VectorStore,
) -> list[dict]:
    """
    子 chunk → 父 chunk 展开。

    通过子 chunk 的 parent_id 找到父 chunk，去重后返回。
    保留原始子 chunk 的 rrf_score 作为排序依据。
    """
    parent_ids = []
    parent_scores = {}

    for child in child_results:
        pid = child.get("metadata", {}).get("parent_id")
        if pid and pid not in parent_scores:
            parent_ids.append(pid)
            parent_scores[pid] = child.get("rrf_score", child.get("score", 0))

    if not parent_ids:
        return child_results

    parents = vector_store.get_by_ids(parent_ids)

    # 按原始子 chunk 的排序（rrf_score）排列
    result = []
    for parent in parents:
        parent["rrf_score"] = parent_scores.get(parent["id"], 0)
        result.append(parent)

    result.sort(key=lambda x: x.get("rrf_score", 0), reverse=True)
    return result


class HybridSearcher:
    """混合检索器"""

    def __init__(
        self,
        vector_store: VectorStore,
        bm25_store: BM25Store,
        embedder: Embedder,
        reranker=None,
    ):
        self.vector_store = vector_store
        self.bm25_store = bm25_store
        self.embedder = embedder
        self.reranker = reranker

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict | None = None,
        use_rerank: bool = True,
        expand_parents: bool = True,
    ) -> list[dict]:
        """
        完整混合检索流程。

        1. 元数据过滤（如有 filters）
        2. 向量检索 top20 + BM25 top20
        3. RRF 融合 → top10
        4. Reranker 精排 → top_k（如有 reranker）
        5. 子 chunk → 父 chunk 展开（如 expand_parents）

        参数:
            query: 检索查询
            top_k: 最终返回数量
            filters: 元数据过滤条件
            use_rerank: 是否使用 Reranker
            expand_parents: 是否展开为父 chunk

        返回: [{id, text, score/rrf_score, metadata}]
        """
        # 构建向量检索的 where 条件
        where = None
        if filters:
            where_conditions = []
            if filters.get("date_from"):
                where_conditions.append({"publish_date": {"$gte": filters["date_from"]}})
            if filters.get("date_to"):
                where_conditions.append({"publish_date": {"$lte": filters["date_to"]}})
            if filters.get("issuing_authority"):
                where_conditions.append({"issuing_authority": filters["issuing_authority"]})
            if filters.get("category"):
                where_conditions.append({"category": filters["category"]})

            # 只搜子 chunk
            where_conditions.append({"role": "child"})

            if len(where_conditions) == 1:
                where = where_conditions[0]
            elif where_conditions:
                where = {"$and": where_conditions}
        else:
            where = {"role": "child"}

        # 1. 向量检索
        query_embedding = self.embedder.embed(query)
        vector_results = self.vector_store.query(
            embedding=query_embedding,
            top_k=20,
            where=where,
        )

        # 2. BM25 检索
        bm25_results = self.bm25_store.search(query, top_k=20)

        # 3. RRF 融合
        rrf_top = 10 if (use_rerank and self.reranker) else top_k
        merged = rrf_merge(vector_results, bm25_results, top_k=rrf_top)

        # 4. Reranker 精排
        if use_rerank and self.reranker and merged:
            merged = self.reranker.rerank(query, merged, top_k=top_k)

        # 5. 父 chunk 展开
        if expand_parents and merged:
            return resolve_parents(merged, self.vector_store)

        return merged[:top_k]
