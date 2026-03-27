# 模块接口约定

## ingestion/loader.py

```python
def load_file(file_path: str) -> dict:
    """
    解析单个 HTML 或 PDF 文件
    返回:
    {
        "text": str,        # 提取的纯文本
        "source": str,      # 文件名（不含路径）
        "title": str,       # 文档标题
        "file_type": str    # "html" | "pdf"
    }
    """

def load_all(data_dir: str) -> list[dict]:
    """扫描目录，加载所有 HTML/PDF 文件，返回 Document 列表"""
```

## ingestion/chunker.py

```python
def chunk_document(doc: dict, chunk_size: int, overlap: int) -> list[dict]:
    """
    将单个文档切分为多个 chunk
    返回 Chunk 列表，每个 chunk:
    {
        "text": str,
        "source": str,
        "title": str,
        "chunk_index": int
    }
    """

def chunk_all(docs: list[dict], chunk_size: int, overlap: int) -> list[dict]:
    """批量分块"""
```

## retrieval/embedder.py

```python
class Embedder:
    def __init__(self, model_name: str): ...

    def embed(self, text: str) -> list[float]:
        """生成单条文本的向量"""

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量生成向量"""
```

## retrieval/store.py

```python
class PolicyStore:
    def __init__(self, chroma_path: str, collection_name: str): ...

    def add_chunks(self, chunks: list[dict], embeddings: list[list[float]]) -> None:
        """批量写入 chunks 和对应向量"""

    def query(self, query_embedding: list[float], top_k: int) -> list[dict]:
        """
        检索 top-k 相关 chunks
        返回列表，每项:
        {
            "text": str,
            "source": str,
            "title": str,
            "chunk_index": int,
            "score": float
        }
        """

    def get_by_source(self, source: str) -> list[dict]:
        """获取某个文件的所有 chunks"""
```

## agent/agent.py

```python
class PolicyAgent:
    def __init__(self): ...

    def chat(self, user_message: str, history: list[dict]) -> dict:
        """
        处理一轮对话
        返回:
        {
            "answer": str,          # Claude 的回复
            "sources": list[str]    # 引用的来源文件名列表
        }
        """
```

## web/app.py

```
GET  /              → 返回 index.html
POST /api/chat      → { "message": str, "history": [...] }
                    ← { "answer": str, "sources": [...] }
```
