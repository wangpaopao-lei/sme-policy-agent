import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import config
from src.ingestion.loader import load_all
from src.ingestion.chunker import chunk_all
from src.retrieval.embedder import Embedder
from src.retrieval.store import PolicyStore


def run(data_dir: str = None):
    data_dir = data_dir or "./data"

    print("=== 步骤 1/4：加载文件 ===")
    docs = load_all(data_dir)
    print(f"共加载 {len(docs)} 篇文档\n")

    print("=== 步骤 2/4：文本分块 ===")
    chunks = chunk_all(docs, chunk_size=config.CHUNK_SIZE, overlap=config.CHUNK_OVERLAP)
    print(f"共生成 {len(chunks)} 个 chunks\n")

    print("=== 步骤 3/4：生成向量 ===")
    embedder = Embedder(model_name=config.EMBEDDING_MODEL)
    texts = [c["text"] for c in chunks]
    embeddings = embedder.embed_batch(texts)
    print(f"生成 {len(embeddings)} 条向量\n")

    print("=== 步骤 4/4：写入 ChromaDB ===")
    store = PolicyStore(
        chroma_path=config.CHROMA_PATH,
        collection_name=config.CHROMA_COLLECTION,
    )
    store.add_chunks(chunks, embeddings)
    print(f"数据库共 {store.count()} 个 chunks\n")

    print("=== 摄入完成 ===")
