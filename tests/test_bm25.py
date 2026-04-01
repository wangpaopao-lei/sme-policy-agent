"""BM25 索引测试"""

import os
import tempfile

import pytest

from src.retrieval.bm25_store import BM25Store, _tokenize


# ============================================================
# 分词测试
# ============================================================


class TestTokenize:
    def test_basic_chinese(self):
        tokens = _tokenize("中小微企业贷款贴息政策")
        assert "中小微企业" in tokens
        assert "贷款贴息" in tokens

    def test_filters_short_tokens(self):
        tokens = _tokenize("这是一个测试")
        # 单字符应被过滤
        assert "是" not in tokens
        assert "一" not in tokens

    def test_filters_markdown_syntax(self):
        tokens = _tokenize("### 第一条 **重要内容**")
        assert "#" not in tokens
        assert "**" not in tokens
        # "重要内容" 可能被分为 "重要" + "内容"
        assert "重要" in tokens or "重要内容" in tokens

    def test_custom_dict_works(self):
        """自定义词典应保持专有名词完整"""
        tokens = _tokenize("专精特新小巨人企业认定")
        assert "专精特新" in tokens


# ============================================================
# BM25Store 测试
# ============================================================


class TestBM25Store:
    def _make_store(self):
        store = BM25Store()
        chunks = [
            {"id": "1", "text": "中小微企业贷款贴息比例为年化1.5个百分点", "metadata": {"source": "a.txt"}},
            {"id": "2", "text": "设备更新贷款财政贴息支持经营主体技术改造", "metadata": {"source": "b.txt"}},
            {"id": "3", "text": "跨境电子商务出口退运商品免征进口关税", "metadata": {"source": "c.txt"}},
            {"id": "4", "text": "专精特新中小企业梯度培育管理办法认定条件", "metadata": {"source": "d.txt"}},
            {"id": "5", "text": "企业年金缴费比例不超过职工工资总额的百分之八", "metadata": {"source": "e.txt"}},
        ]
        store.build_index(chunks)
        return store

    def test_basic_search(self):
        store = self._make_store()
        results = store.search("贷款贴息")
        assert len(results) > 0
        assert results[0]["id"] == "1"  # 贷款贴息应排第一

    def test_search_returns_score(self):
        store = self._make_store()
        results = store.search("贷款贴息")
        for r in results:
            assert "score" in r
            assert r["score"] > 0

    def test_search_respects_top_k(self):
        store = self._make_store()
        results = store.search("企业", top_k=2)
        assert len(results) <= 2

    def test_search_includes_metadata(self):
        store = self._make_store()
        results = store.search("跨境电商")
        if results:
            assert "metadata" in results[0]
            assert results[0]["metadata"]["source"] == "c.txt"

    def test_keyword_search(self):
        """精确关键词匹配"""
        store = self._make_store()
        results = store.search("专精特新")
        assert any(r["id"] == "4" for r in results)

    def test_empty_query(self):
        store = self._make_store()
        results = store.search("")
        assert results == []

    def test_no_match(self):
        store = self._make_store()
        results = store.search("完全无关的查询词汇xyz")
        # 可能有低分结果，但不应崩溃
        assert isinstance(results, list)

    def test_empty_store(self):
        store = BM25Store()
        store.build_index([])
        results = store.search("测试")
        assert results == []

    def test_count(self):
        store = self._make_store()
        assert store.count() == 5


class TestWeightedKeywords:
    def test_weighted_keywords_boost(self):
        store = BM25Store()
        chunks = [
            {"id": "1", "text": "关于中小微企业发展的一般政策文件和说明", "metadata": {}},
            {"id": "2", "text": "关于产业升级的另一个政策文件内容说明", "metadata": {}},
            {"id": "3", "text": "跨境电子商务出口退运商品免征进口关税消费税", "metadata": {}},
        ]
        store.build_index(chunks)

        # 给 chunk 2 添加加权关键词
        store.add_weighted_keywords("2", {"融资担保": 5, "贷款贴息": 3})

        results = store.search("融资担保贷款贴息")
        # chunk 2 应该因为加权关键词而排在前面
        assert len(results) > 0
        assert results[0]["id"] == "2"

    def test_nonexistent_chunk_id(self):
        """不存在的 chunk_id 不应崩溃"""
        store = BM25Store()
        store.build_index([{"id": "1", "text": "内容", "metadata": {}}])
        store.add_weighted_keywords("不存在的id", {"关键词": 5})
        # 不应崩溃


class TestPersistence:
    def test_save_and_load(self):
        store = BM25Store()
        chunks = [
            {"id": "1", "text": "中小微企业贷款贴息比例为年化1.5个百分点", "metadata": {"source": "a.txt"}},
            {"id": "2", "text": "设备更新技术改造数字化智能化绿色化", "metadata": {"source": "b.txt"}},
            {"id": "3", "text": "跨境电子商务出口退运商品免征进口关税", "metadata": {"source": "c.txt"}},
        ]
        store.build_index(chunks)

        # 保存
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            tmp_path = f.name
        store.save(tmp_path)

        # 加载到新 store
        new_store = BM25Store()
        new_store.load(tmp_path)

        os.unlink(tmp_path)

        # 验证加载后的 store 可以正常检索
        assert new_store.count() == 3
        results = new_store.search("贷款贴息")
        assert len(results) > 0
        assert results[0]["id"] == "1"
