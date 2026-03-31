"""BGE Reranker 精排

使用 BGE-Reranker-v2-m3 对粗排结果进行精排。
模型本地部署，无 API 成本。
"""

from __future__ import annotations


class Reranker:
    """Cross-encoder Reranker"""

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3", max_length: int = 512):
        """
        初始化 Reranker。

        参数:
            model_name: cross-encoder 模型名
            max_length: 输入最大长度
        """
        from sentence_transformers import CrossEncoder
        self.model = CrossEncoder(model_name, max_length=max_length)

    def rerank(self, query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
        """
        对候选结果重排序。

        参数:
            query: 查询文本
            candidates: [{id, text, ...}] 候选列表
            top_k: 返回数量

        返回: 重排后的 top_k 结果（保留原有字段，添加 rerank_score）
        """
        if not candidates:
            return []

        # 构造 query-document 对
        pairs = [(query, c["text"]) for c in candidates]

        # 打分
        scores = self.model.predict(pairs)

        # 按分数排序
        scored = list(zip(candidates, scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for doc, score in scored[:top_k]:
            doc = doc.copy()
            doc["rerank_score"] = float(score)
            results.append(doc)

        return results
