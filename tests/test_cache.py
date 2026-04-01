"""语义缓存测试"""

import os
import tempfile
import time

from unittest.mock import MagicMock

import pytest

from src.conversation.cache import SemanticCache


def _make_mock_embedder():
    """构造 mock embedder，返回固定维度的向量"""
    mock = MagicMock()
    call_count = [0]

    def embed_fn(text):
        call_count[0] += 1
        # 简单的 hash 向量（确保相同文本返回相同向量）
        import hashlib
        h = hashlib.md5(text.encode()).hexdigest()
        vec = [int(c, 16) / 15.0 for c in h]  # 32 维向量
        # 归一化
        import math
        norm = math.sqrt(sum(x * x for x in vec))
        return [x / norm for x in vec]

    mock.embed = embed_fn
    mock.call_count = call_count
    return mock


class TestSemanticCacheBasic:
    def _make_cache(self, **kwargs):
        embedder = _make_mock_embedder()
        db_path = tempfile.mktemp(suffix=".db")
        cache = SemanticCache(
            embedder=embedder,
            db_path=db_path,
            max_size=kwargs.get("max_size", 100),
            ttl=kwargs.get("ttl", 3600),
            threshold=kwargs.get("threshold", 0.92),
        )
        return cache, db_path

    def test_set_and_get_exact(self):
        """相同 query 应命中"""
        cache, db_path = self._make_cache(threshold=0.99)
        try:
            cache.set("贷款贴息比例是多少", "1.5个百分点", ["a.txt"])

            result = cache.get("贷款贴息比例是多少")
            assert result is not None
            answer, sources = result
            assert answer == "1.5个百分点"
            assert sources == ["a.txt"]
        finally:
            os.unlink(db_path)

    def test_miss_different_query(self):
        """完全不同的 query 不应命中"""
        cache, db_path = self._make_cache(threshold=0.99)
        try:
            cache.set("贷款贴息比例是多少", "1.5个百分点", ["a.txt"])

            result = cache.get("完全不同的问题关于天气")
            assert result is None
        finally:
            os.unlink(db_path)

    def test_count(self):
        cache, db_path = self._make_cache()
        try:
            assert cache.count() == 0
            cache.set("问题1", "回答1", ["a.txt"])
            assert cache.count() == 1
            cache.set("问题2", "回答2", ["b.txt"])
            assert cache.count() == 2
        finally:
            os.unlink(db_path)

    def test_clear(self):
        cache, db_path = self._make_cache()
        try:
            cache.set("问题", "回答", ["a.txt"])
            cache.clear()
            assert cache.count() == 0
            assert cache.get("问题") is None
        finally:
            os.unlink(db_path)


class TestSemanticCacheLRU:
    def test_lru_eviction(self):
        """超过 max_size 时应淘汰最久未访问的"""
        embedder = _make_mock_embedder()
        db_path = tempfile.mktemp(suffix=".db")
        cache = SemanticCache(
            embedder=embedder,
            db_path=db_path,
            max_size=2,
            ttl=3600,
            threshold=0.99,
        )
        try:
            cache.set("问题A", "回答A", ["a.txt"])
            cache.set("问题B", "回答B", ["b.txt"])
            cache.set("问题C", "回答C", ["c.txt"])  # 应该淘汰 A

            assert cache.count() == 2
        finally:
            os.unlink(db_path)


class TestSemanticCacheTTL:
    def test_ttl_expiration(self):
        """过期条目不应被返回"""
        embedder = _make_mock_embedder()
        db_path = tempfile.mktemp(suffix=".db")
        cache = SemanticCache(
            embedder=embedder,
            db_path=db_path,
            max_size=100,
            ttl=1,  # 1 秒过期
            threshold=0.99,
        )
        try:
            cache.set("问题", "回答", ["a.txt"])
            time.sleep(1.5)  # 等待过期

            result = cache.get("问题")
            assert result is None
        finally:
            os.unlink(db_path)


class TestSemanticCacheSourceInvalidation:
    def test_invalidate_by_source(self):
        """按 source 清除缓存"""
        embedder = _make_mock_embedder()
        db_path = tempfile.mktemp(suffix=".db")
        cache = SemanticCache(
            embedder=embedder,
            db_path=db_path,
            max_size=100,
            ttl=3600,
            threshold=0.99,
        )
        try:
            cache.set("关于A的问题", "回答A", ["a.txt"])
            cache.set("关于B的问题", "回答B", ["b.txt"])
            cache.set("关于AB的问题", "回答AB", ["a.txt", "b.txt"])

            # 清除引用了 a.txt 的缓存
            removed = cache.invalidate_by_source("a.txt")
            assert removed == 2  # A 和 AB
            assert cache.count() == 1  # 只剩 B
        finally:
            os.unlink(db_path)

    def test_invalidate_nonexistent_source(self):
        """清除不存在的 source 不应出错"""
        embedder = _make_mock_embedder()
        db_path = tempfile.mktemp(suffix=".db")
        cache = SemanticCache(
            embedder=embedder,
            db_path=db_path,
            max_size=100,
            ttl=3600,
            threshold=0.99,
        )
        try:
            cache.set("问题", "回答", ["a.txt"])
            removed = cache.invalidate_by_source("不存在.txt")
            assert removed == 0
            assert cache.count() == 1
        finally:
            os.unlink(db_path)


class TestSemanticCachePersistence:
    def test_persistence(self):
        """关闭后重新加载应保留数据"""
        embedder = _make_mock_embedder()
        db_path = tempfile.mktemp(suffix=".db")

        try:
            # 第一次：写入
            cache1 = SemanticCache(
                embedder=embedder, db_path=db_path,
                max_size=100, ttl=3600, threshold=0.99,
            )
            cache1.set("问题", "回答", ["a.txt"])
            assert cache1.count() == 1

            # 第二次：重新加载
            cache2 = SemanticCache(
                embedder=embedder, db_path=db_path,
                max_size=100, ttl=3600, threshold=0.99,
            )
            assert cache2.count() == 1
            result = cache2.get("问题")
            assert result is not None
            assert result[0] == "回答"
        finally:
            os.unlink(db_path)
