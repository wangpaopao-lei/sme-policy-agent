import hashlib
import chromadb


def _chunk_id(source: str, chunk_index: int) -> str:
    """生成稳定的 chunk ID"""
    raw = f"{source}::{chunk_index}"
    return hashlib.md5(raw.encode()).hexdigest()


class PolicyStore:
    def __init__(self, chroma_path: str, collection_name: str):
        self.client = chromadb.PersistentClient(path=chroma_path)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks: list[dict], embeddings: list[list[float]]) -> None:
        ids = [_chunk_id(c["source"], c["chunk_index"]) for c in chunks]
        documents = [c["text"] for c in chunks]
        metadatas = [
            {
                "source": c["source"],
                "title": c["title"],
                "chunk_index": c["chunk_index"],
            }
            for c in chunks
        ]

        # 跳过已存在的 ID
        existing = set(self.collection.get(ids=ids)["ids"])
        new_indices = [i for i, id_ in enumerate(ids) if id_ not in existing]

        if not new_indices:
            print("  所有 chunks 已存在，跳过写入")
            return

        self.collection.add(
            ids=[ids[i] for i in new_indices],
            embeddings=[embeddings[i] for i in new_indices],
            documents=[documents[i] for i in new_indices],
            metadatas=[metadatas[i] for i in new_indices],
        )
        print(f"  写入 {len(new_indices)} 个 chunks（跳过 {len(existing)} 个已存在）")

    def query(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        chunks = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            chunks.append({
                "text": doc,
                "source": meta["source"],
                "title": meta["title"],
                "chunk_index": meta["chunk_index"],
                "score": round(1 - dist, 4),  # cosine distance → similarity
            })
        return chunks

    def get_by_source(self, source: str) -> list[dict]:
        results = self.collection.get(
            where={"source": source},
            include=["documents", "metadatas"],
        )

        chunks = []
        for doc, meta in zip(results["documents"], results["metadatas"]):
            chunks.append({
                "text": doc,
                "source": meta["source"],
                "title": meta["title"],
                "chunk_index": meta["chunk_index"],
            })

        chunks.sort(key=lambda x: x["chunk_index"])
        return chunks

    def count(self) -> int:
        return self.collection.count()
