import sys
import os
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingestion.chunker import chunk_document, chunk_all
from src.retrieval.store import PolicyStore, _chunk_id


# ── 测试 chunker ──────────────────────────────────────────────────────────────

def _make_doc(text: str, source: str = "test.html", title: str = "测试文档") -> dict:
    return {"text": text, "source": source, "title": title, "file_type": "html"}


def test_chunk_short_doc_produces_single_chunk():
    doc = _make_doc("这是一段很短的文字。")
    chunks = chunk_document(doc, chunk_size=400, overlap=50)
    assert len(chunks) == 1
    assert chunks[0]["text"] == "这是一段很短的文字。"
    assert chunks[0]["chunk_index"] == 0


def test_chunk_long_doc_splits_into_multiple_chunks():
    # 构造超过 400 字的文本，分成多个段落
    paragraphs = ["这是第{}段政策内容，包含一些描述文字。".format(i) * 3 for i in range(20)]
    doc = _make_doc("\n".join(paragraphs))
    chunks = chunk_document(doc, chunk_size=400, overlap=50)
    assert len(chunks) > 1


def test_chunk_indices_are_sequential():
    paragraphs = ["段落{}：".format(i) + "内容" * 20 for i in range(10)]
    doc = _make_doc("\n".join(paragraphs))
    chunks = chunk_document(doc, chunk_size=100, overlap=0)
    indices = [c["chunk_index"] for c in chunks]
    assert indices == list(range(len(chunks)))


def test_chunk_preserves_metadata():
    doc = _make_doc("内容", source="policy.pdf", title="重要政策")
    chunks = chunk_document(doc)
    assert chunks[0]["source"] == "policy.pdf"
    assert chunks[0]["title"] == "重要政策"


def test_chunk_no_empty_chunks():
    doc = _make_doc("段落一\n\n\n段落二\n\n段落三")
    chunks = chunk_document(doc)
    for chunk in chunks:
        assert chunk["text"].strip(), "不应产生空 chunk"


def test_chunk_all_aggregates_multiple_docs():
    docs = [
        _make_doc("文档A内容" * 5, source="a.html"),
        _make_doc("文档B内容" * 5, source="b.html"),
    ]
    chunks = chunk_all(docs, chunk_size=400, overlap=50)
    sources = {c["source"] for c in chunks}
    assert "a.html" in sources
    assert "b.html" in sources


def test_chunk_size_respected():
    # 每段 100 字，chunk_size=150，相邻两段合并后超过 150 才切割
    para = "政" * 100
    doc = _make_doc("\n".join([para] * 5))
    chunks = chunk_document(doc, chunk_size=150, overlap=0)
    for chunk in chunks[:-1]:  # 最后一块可以短
        assert len(chunk["text"]) <= 300, "单块不应远超 chunk_size 两倍"


# ── 测试 store ────────────────────────────────────────────────────────────────

def _fake_embedding(dim: int = 8) -> list[float]:
    """生成固定维度的假向量（归一化）"""
    import math
    val = 1.0 / math.sqrt(dim)
    return [val] * dim


@pytest.fixture
def tmp_store(tmp_path):
    """每个测试用独立的临时 ChromaDB"""
    store = PolicyStore(
        chroma_path=str(tmp_path / "chroma"),
        collection_name="test_collection",
    )
    return store


def test_store_add_and_count(tmp_store):
    chunks = [
        {"text": "政策内容A", "source": "a.html", "title": "文档A", "chunk_index": 0},
        {"text": "政策内容B", "source": "a.html", "title": "文档A", "chunk_index": 1},
    ]
    embeddings = [_fake_embedding() for _ in chunks]
    tmp_store.add_chunks(chunks, embeddings)
    assert tmp_store.count() == 2


def test_store_no_duplicate_on_readd(tmp_store):
    chunks = [{"text": "内容", "source": "a.html", "title": "文档A", "chunk_index": 0}]
    embeddings = [_fake_embedding()]
    tmp_store.add_chunks(chunks, embeddings)
    tmp_store.add_chunks(chunks, embeddings)  # 重复写入
    assert tmp_store.count() == 1


def test_store_query_returns_top_k(tmp_store):
    chunks = [
        {"text": f"政策片段{i}", "source": "a.html", "title": "文档A", "chunk_index": i}
        for i in range(5)
    ]
    embeddings = [_fake_embedding() for _ in chunks]
    tmp_store.add_chunks(chunks, embeddings)

    results = tmp_store.query(_fake_embedding(), top_k=3)
    assert len(results) == 3


def test_store_query_result_fields(tmp_store):
    chunks = [{"text": "内容", "source": "a.html", "title": "文档A", "chunk_index": 0}]
    tmp_store.add_chunks(chunks, [_fake_embedding()])

    results = tmp_store.query(_fake_embedding(), top_k=1)
    assert len(results) == 1
    r = results[0]
    assert "text" in r
    assert "source" in r
    assert "title" in r
    assert "chunk_index" in r
    assert "score" in r
    assert 0.0 <= r["score"] <= 1.0


def test_store_get_by_source(tmp_store):
    chunks = [
        {"text": f"片段{i}", "source": "policy.html", "title": "政策", "chunk_index": i}
        for i in range(3)
    ]
    other = [{"text": "其他", "source": "other.html", "title": "其他", "chunk_index": 0}]
    tmp_store.add_chunks(chunks + other, [_fake_embedding()] * 4)

    results = tmp_store.get_by_source("policy.html")
    assert len(results) == 3
    assert all(r["source"] == "policy.html" for r in results)
    # 验证按 chunk_index 排序
    assert [r["chunk_index"] for r in results] == [0, 1, 2]


def test_chunk_id_is_deterministic():
    id1 = _chunk_id("a.html", 0)
    id2 = _chunk_id("a.html", 0)
    assert id1 == id2


def test_chunk_id_differs_by_source_or_index():
    assert _chunk_id("a.html", 0) != _chunk_id("b.html", 0)
    assert _chunk_id("a.html", 0) != _chunk_id("a.html", 1)
