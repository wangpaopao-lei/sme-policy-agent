"""向量数据库封装（ChromaDB）

重构自 store.py，支持父子 chunk 的 metadata 和按 ID 批量查询。
旧的 store.py 保留不动（v1 pipeline 仍在使用）。
"""

import chromadb


class VectorStore:
    def __init__(self, chroma_path: str, collection_name: str):
        self.client = chromadb.PersistentClient(path=chroma_path)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    @staticmethod
    def _dedup_indices(ids: list[str]) -> list[int]:
        """返回去重后每个 ID 第一次出现的索引列表"""
        seen = set()
        result = []
        for i, id_ in enumerate(ids):
            if id_ not in seen:
                seen.add(id_)
                result.append(i)
        return result

    def _get_existing_ids(self, ids: list[str]) -> set[str]:
        """查询已存在的 ID（先去重，避免 ChromaDB DuplicateIDError）"""
        unique_ids = list(set(ids))
        if not unique_ids:
            return set()
        return set(self.collection.get(ids=unique_ids)["ids"])

    def add_chunks(self, chunks: list[dict], embeddings: list[list[float]]) -> None:
        """
        写入 chunks 和向量。支持任意 metadata（含 role, parent_id 等）。

        参数:
            chunks: [{id, text, metadata}]
            embeddings: 对应的向量列表
        """
        ids = [c["id"] for c in chunks]
        documents = [c["text"] for c in chunks]

        # ChromaDB metadata 只支持 str/int/float/bool
        metadatas = []
        for c in chunks:
            meta = {}
            for k, v in c.get("metadata", {}).items():
                if isinstance(v, (str, int, float, bool)):
                    meta[k] = v
            metadatas.append(meta)

        # 输入去重 + 跳过已存在的 ID
        dedup = self._dedup_indices(ids)
        existing = self._get_existing_ids(ids)
        new_indices = [i for i in dedup if ids[i] not in existing]

        if not new_indices:
            return

        self.collection.add(
            ids=[ids[i] for i in new_indices],
            embeddings=[embeddings[i] for i in new_indices] if embeddings else None,
            documents=[documents[i] for i in new_indices],
            metadatas=[metadatas[i] for i in new_indices],
        )

    def add_chunks_without_embeddings(self, chunks: list[dict]) -> None:
        """写入不需要 embedding 的 chunks（如父 chunk，只用于展开阅读）"""
        ids = [c["id"] for c in chunks]
        documents = [c["text"] for c in chunks]

        metadatas = []
        for c in chunks:
            meta = {}
            for k, v in c.get("metadata", {}).items():
                if isinstance(v, (str, int, float, bool)):
                    meta[k] = v
            metadatas.append(meta)

        dedup = self._dedup_indices(ids)
        existing = self._get_existing_ids(ids)
        new_indices = [i for i in dedup if ids[i] not in existing]

        if not new_indices:
            return

        self.collection.add(
            ids=[ids[i] for i in new_indices],
            documents=[documents[i] for i in new_indices],
            metadatas=[metadatas[i] for i in new_indices],
        )

    def query(
        self,
        embedding: list[float],
        top_k: int = 20,
        where: dict | None = None,
    ) -> list[dict]:
        """
        向量检索。

        参数:
            embedding: 查询向量
            top_k: 返回数量
            where: 元数据过滤条件（ChromaDB where 格式）

        返回: [{id, text, score, metadata}]
        """
        kwargs = {
            "query_embeddings": [embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = self.collection.query(**kwargs)

        chunks = []
        for id_, doc, meta, dist in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            chunks.append({
                "id": id_,
                "text": doc,
                "score": round(1 - dist, 4),
                "metadata": meta,
            })
        return chunks

    def get_by_ids(self, ids: list[str]) -> list[dict]:
        """按 ID 批量获取 chunks"""
        if not ids:
            return []

        results = self.collection.get(
            ids=ids,
            include=["documents", "metadatas"],
        )

        chunks = []
        for id_, doc, meta in zip(results["ids"], results["documents"], results["metadatas"]):
            chunks.append({
                "id": id_,
                "text": doc,
                "metadata": meta,
            })
        return chunks

    def get_by_source(self, source: str) -> list[dict]:
        """获取某文件所有 chunks"""
        results = self.collection.get(
            where={"source": source},
            include=["documents", "metadatas"],
        )

        chunks = []
        for id_, doc, meta in zip(results["ids"], results["documents"], results["metadatas"]):
            chunks.append({
                "id": id_,
                "text": doc,
                "metadata": meta,
            })
        return chunks

    def count(self) -> int:
        return self.collection.count()

    def clear(self) -> None:
        """清空 collection"""
        self.client.delete_collection(self.collection.name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection.name,
            metadata={"hnsw:space": "cosine"},
        )
