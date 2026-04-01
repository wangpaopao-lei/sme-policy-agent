"""语义缓存

基于 Embedding 相似度匹配缓存，避免重复检索和 LLM 调用。
支持 LRU 淘汰 + TTL 过期 + source 关联失效。
持久化到 SQLite。
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections import OrderedDict
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    pass


class SemanticCache:
    """语义缓存：相似问题直接返回缓存的回答"""

    def __init__(
        self,
        embedder,
        db_path: str = "cache/semantic_cache.db",
        max_size: int = 1000,
        ttl: int = 86400,
        threshold: float = 0.92,
    ):
        """
        参数:
            embedder: Embedding 模型实例（需要有 embed(text) 方法）
            db_path: SQLite 数据库路径
            max_size: 最大缓存条目数（LRU 淘汰）
            ttl: 缓存过期时间（秒，默认 24 小时）
            threshold: 语义相似度阈值（高于此值视为命中）
        """
        self.embedder = embedder
        self.max_size = max_size
        self.ttl = ttl
        self.threshold = threshold

        # 内存缓存（OrderedDict 支持 LRU）
        self._cache: OrderedDict[str, dict] = OrderedDict()

        # SQLite 持久化
        self._db_path = db_path
        self._init_db()
        self._load_from_db()

    def _init_db(self) -> None:
        """初始化 SQLite 表"""
        import os
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)

        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                query TEXT,
                embedding BLOB,
                answer TEXT,
                sources TEXT,
                timestamp REAL,
                last_accessed REAL
            )
        """)
        conn.commit()
        conn.close()

    def _load_from_db(self) -> None:
        """从 SQLite 加载缓存到内存"""
        conn = sqlite3.connect(self._db_path)
        rows = conn.execute(
            "SELECT key, query, embedding, answer, sources, timestamp, last_accessed "
            "FROM cache ORDER BY last_accessed ASC"
        ).fetchall()
        conn.close()

        for key, query, emb_blob, answer, sources_json, ts, last_acc in rows:
            embedding = np.frombuffer(emb_blob, dtype=np.float32).tolist()
            sources = json.loads(sources_json)
            self._cache[key] = {
                "query": query,
                "embedding": embedding,
                "answer": answer,
                "sources": sources,
                "timestamp": ts,
                "last_accessed": last_acc,
            }

    def _save_entry(self, key: str, entry: dict) -> None:
        """保存单条到 SQLite"""
        conn = sqlite3.connect(self._db_path)
        emb_blob = np.array(entry["embedding"], dtype=np.float32).tobytes()
        sources_json = json.dumps(entry["sources"], ensure_ascii=False)

        conn.execute(
            "INSERT OR REPLACE INTO cache (key, query, embedding, answer, sources, timestamp, last_accessed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (key, entry["query"], emb_blob, entry["answer"], sources_json,
             entry["timestamp"], entry["last_accessed"]),
        )
        conn.commit()
        conn.close()

    def _delete_entry(self, key: str) -> None:
        """从 SQLite 删除"""
        conn = sqlite3.connect(self._db_path)
        conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        conn.commit()
        conn.close()

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """计算余弦相似度"""
        a_arr = np.array(a)
        b_arr = np.array(b)
        dot = np.dot(a_arr, b_arr)
        norm = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
        if norm == 0:
            return 0.0
        return float(dot / norm)

    def get(self, query: str) -> tuple[str, list[str]] | None:
        """
        查询缓存。

        返回 (answer, sources) 或 None（未命中）。
        """
        if not self._cache:
            return None

        query_embedding = self.embedder.embed(query)
        now = time.time()

        best_key = None
        best_score = 0.0

        keys_to_delete = []

        for key, entry in self._cache.items():
            # TTL 检查
            if now - entry["timestamp"] > self.ttl:
                keys_to_delete.append(key)
                continue

            score = self._cosine_similarity(query_embedding, entry["embedding"])
            if score > best_score:
                best_score = score
                best_key = key

        # 清理过期条目
        for key in keys_to_delete:
            del self._cache[key]
            self._delete_entry(key)

        if best_key and best_score >= self.threshold:
            # 命中：更新 LRU 顺序和访问时间
            entry = self._cache[best_key]
            self._cache.move_to_end(best_key)
            entry["last_accessed"] = now
            self._save_entry(best_key, entry)
            return entry["answer"], entry["sources"]

        return None

    def set(self, query: str, answer: str, sources: list[str]) -> None:
        """
        写入缓存。
        """
        now = time.time()
        embedding = self.embedder.embed(query)

        # 用 embedding 的 hash 作为 key（避免完全相同的 query 重复）
        key = str(hash(tuple(round(x, 6) for x in embedding[:10])))

        entry = {
            "query": query,
            "embedding": embedding,
            "answer": answer,
            "sources": sources,
            "timestamp": now,
            "last_accessed": now,
        }

        # LRU 淘汰
        if len(self._cache) >= self.max_size and key not in self._cache:
            oldest_key, _ = self._cache.popitem(last=False)
            self._delete_entry(oldest_key)

        self._cache[key] = entry
        self._cache.move_to_end(key)
        self._save_entry(key, entry)

    def invalidate_by_source(self, source: str) -> int:
        """
        某文档更新时，清除引用了该文档的缓存条目。

        返回: 清除的条目数
        """
        keys_to_delete = []
        for key, entry in self._cache.items():
            if source in entry["sources"]:
                keys_to_delete.append(key)

        for key in keys_to_delete:
            del self._cache[key]
            self._delete_entry(key)

        return len(keys_to_delete)

    def clear(self) -> None:
        """清空所有缓存"""
        self._cache.clear()
        conn = sqlite3.connect(self._db_path)
        conn.execute("DELETE FROM cache")
        conn.commit()
        conn.close()

    def count(self) -> int:
        return len(self._cache)

    @property
    def hit_rate_info(self) -> str:
        """返回缓存状态信息"""
        return f"缓存条目: {len(self._cache)}/{self.max_size}"
