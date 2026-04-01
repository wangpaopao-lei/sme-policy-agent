"""
v2 数据摄入脚本

完整流程：
  1. 文档解析 + 元数据提取 + 表格处理（pipeline_v2）
  2. 父子 chunk 分块
  3. 子 chunk Embedding
  4. 写入双索引（ChromaDB 向量 + BM25 关键词）

用法：
    python scripts/ingest_v2.py                  # 默认（开启 LLM）
    python scripts/ingest_v2.py --no-llm         # 跳过 LLM 兜底
    python scripts/ingest_v2.py --clean           # 清空后重新入库
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config


def ingest(
    data_dir: str = "data",
    output_dir: str = "data/parsed",
    use_llm: bool = True,
    clean: bool = False,
):
    """完整 v2 摄入流程"""
    from src.ingestion.pipeline_v2 import run_pipeline
    from src.chunking.parent_child import create_parent_child_chunks
    from src.retrieval.embedder import Embedder
    from src.retrieval.vector_store import VectorStore
    from src.retrieval.bm25_store import BM25Store

    # === 步骤 1：文档解析 ===
    print("=" * 60)
    print("步骤 1/5：文档解析 + 元数据 + 表格处理")
    print("=" * 60)
    pipeline_result = run_pipeline(
        data_dir=data_dir,
        output_dir=output_dir,
        use_llm=use_llm,
    )

    documents = pipeline_result["documents"]
    if not documents:
        print("\n[ERROR] 没有成功解析的文档，退出")
        return

    # === 步骤 2：父子分块 ===
    print(f"\n{'=' * 60}")
    print("步骤 2/5：父子 chunk 分块")
    print("=" * 60)

    all_parents = []
    all_children = []

    for doc in documents:
        parents, children = create_parent_child_chunks(
            markdown=doc["final_document"],
            metadata=doc["metadata"],
        )
        all_parents.extend(parents)
        all_children.extend(children)
        print(f"  {doc['source']}: {len(parents)} 父 + {len(children)} 子 chunks")

    print(f"\n  合计: {len(all_parents)} 父 + {len(all_children)} 子 chunks")

    # === 步骤 3：Embedding ===
    print(f"\n{'=' * 60}")
    print("步骤 3/5：生成 Embedding")
    print("=" * 60)

    embedder = Embedder(model_name=config.EMBEDDING_MODEL)

    # 子 chunk embedding
    child_texts = [c["text"] for c in all_children]
    child_embeddings = embedder.embed_batch(child_texts)
    print(f"  子 chunks: {len(child_embeddings)} 条向量")

    # 父 chunk 也需要 embedding（ChromaDB 要求同一 collection 维度一致）
    parent_texts = [c["text"] for c in all_parents]
    parent_embeddings = embedder.embed_batch(parent_texts)
    print(f"  父 chunks: {len(parent_embeddings)} 条向量")

    # === 步骤 4：写入 ChromaDB ===
    print(f"\n{'=' * 60}")
    print("步骤 4/5：写入 ChromaDB（向量索引）")
    print("=" * 60)

    vector_store = VectorStore(
        chroma_path=config.CHROMA_PATH,
        collection_name=config.CHROMA_COLLECTION + "_v2",
    )

    if clean:
        print("  清空现有数据...")
        vector_store.clear()

    # 先写子 chunk（确定 collection 维度为 1024）
    vector_store.add_chunks(all_children, child_embeddings)
    print(f"  子 chunks: {len(all_children)} 条")

    # 再写父 chunk（同维度 embedding）
    vector_store.add_chunks(all_parents, parent_embeddings)
    print(f"  父 chunks: {len(all_parents)} 条")
    print(f"  数据库总计: {vector_store.count()} 条")

    # === 步骤 5：构建 BM25 索引 ===
    print(f"\n{'=' * 60}")
    print("步骤 5/5：构建 BM25 关键词索引")
    print("=" * 60)

    bm25_store = BM25Store()

    # BM25 只索引子 chunk（和向量检索对齐）
    bm25_chunks = [
        {"id": c["id"], "text": c["text"], "metadata": c["metadata"]}
        for c in all_children
    ]
    bm25_store.build_index(bm25_chunks)

    # 表格加权关键词
    table_keyword_count = 0
    for doc in documents:
        for table in doc.get("tables", []):
            keywords = table.get("keywords", {})
            if keywords:
                # 找到包含该表格内容的子 chunk
                table_md = table.get("markdown", "")
                for child in all_children:
                    if child["metadata"].get("source") == doc["source"]:
                        # 简单匹配：表格文本在子 chunk 中出现
                        if table_md[:50] in child["text"]:
                            bm25_store.add_weighted_keywords(child["id"], keywords)
                            table_keyword_count += 1
                            break

    bm25_path = os.path.join(config.CHROMA_PATH, "bm25_index.pkl")
    bm25_store.save(bm25_path)
    print(f"  索引 {bm25_store.count()} 个子 chunks")
    print(f"  表格加权关键词: {table_keyword_count} 个表格")
    print(f"  保存到: {bm25_path}")

    # === 完成 ===
    print(f"\n{'=' * 60}")
    print("摄入完成!")
    print(f"  文档: {len(documents)} 篇")
    print(f"  父 chunks: {len(all_parents)}")
    print(f"  子 chunks: {len(all_children)}")
    print(f"  向量索引: {vector_store.count()} 条")
    print(f"  BM25 索引: {bm25_store.count()} 条")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="v2 数据摄入")
    parser.add_argument("--no-llm", action="store_true", help="跳过 LLM 兜底")
    parser.add_argument("--clean", action="store_true", help="清空后重新入库")
    parser.add_argument("--data-dir", default="data", help="原始文件目录")
    parser.add_argument("--output-dir", default="data/parsed", help="输出目录")
    args = parser.parse_args()

    ingest(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        use_llm=not args.no_llm,
        clean=args.clean,
    )
