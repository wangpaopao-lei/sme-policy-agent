# 模块接口约定

## 文档处理层（Phase 1）

### ingestion/parsers/pdf_parser.py

```python
def parse_pdf(file_path: str) -> dict:
    """
    解析 PDF 文件，提取文本和表格
    返回:
    {
        "markdown": str,           # 结构化 Markdown 文本
        "tables": list[dict],      # 提取的表格列表
        "raw_text": str,           # 原始文本（用于元数据提取）
        "source": str,             # 文件名
        "file_type": "pdf"
    }
    tables 中每项:
    {
        "markdown": str,           # Markdown 表格
        "natural_language": str,   # 自然语言描述
        "page": int                # 所在页码
    }
    """
```

### ingestion/parsers/html_parser.py

```python
def parse_html(file_path: str) -> dict:
    """
    解析 HTML 文件，转为 Markdown
    返回:
    {
        "markdown": str,
        "tables": list[dict],
        "raw_text": str,
        "source": str,
        "file_type": "html",
        "meta_tags": dict          # HTML meta 标签提取的元数据
    }
    """
```

### ingestion/parsers/md_parser.py

```python
def parse_markdown(file_path: str) -> dict:
    """
    读取 Markdown 文件，标准化格式
    返回:
    {
        "markdown": str,
        "tables": list[dict],
        "raw_text": str,
        "source": str,
        "file_type": "markdown"
    }
    """
```

### ingestion/metadata/regex_extractor.py

```python
def extract_metadata_by_regex(text: str) -> dict:
    """
    正则提取政策文档元数据
    返回（缺失字段为 None）:
    {
        "title": str | None,
        "policy_number": str | None,        # 发文字号
        "issuing_authority": str | None,     # 发文机关
        "publish_date": str | None,          # YYYY-MM-DD
        "effective_date": str | None,
        "expiry_date": str | None,
        "applicable_region": str | None,
        "category": str | None               # 融资支持/税收优惠/人才政策/产业扶持/科技创新/其他
    }
    """
```

### ingestion/metadata/llm_extractor.py

```python
def extract_metadata_by_llm(text: str, missing_fields: list[str]) -> dict:
    """
    用 Haiku 提取正则缺失的元数据字段
    text: 文档前1000字 + 后500字
    missing_fields: 需要提取的字段名列表
    返回: 同 regex_extractor 格式
    """
```

### ingestion/table/table_processor.py

```python
def process_table(table_markdown: str, context: str) -> dict:
    """
    处理单个表格：生成自然语言描述、Questions、Keywords
    table_markdown: Markdown 格式表格
    context: 表格所在的上下文（前后文本）
    返回:
    {
        "markdown": str,                    # 原始 Markdown 表格
        "natural_language": str,            # 自然语言描述
        "questions": list[str],             # LLM 生成的检索问题
        "keywords": dict[str, int]          # 加权关键词 {词: 权重}
    }
    """
```

### ingestion/pipeline.py

```python
def run_pipeline(data_dir: str, output_dir: str) -> dict:
    """
    完整摄入流水线：解析 → 标准化 → 元数据 → 表格处理 → 输出
    data_dir: 原始文件目录 (data/raw/)
    output_dir: 输出目录 (data/parsed/)
    返回:
    {
        "total_files": int,
        "processed": int,
        "failed": list[str],
        "documents": list[dict]             # 处理后的文档列表
    }
    """
```

---

## 分块层（Phase 2）

### chunking/structure_splitter.py

```python
def split_by_structure(markdown: str, max_size: int = 1000) -> list[dict]:
    """
    基于 Markdown 标题层级分割
    返回 section 列表:
    {
        "text": str,
        "heading": str,                     # 所属标题
        "level": int                        # 标题层级 (1-3)
    }
    """
```

### chunking/fixed_splitter.py

```python
def split_fixed(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """
    固定长度分割（兜底策略）
    """
```

### chunking/parent_child.py

```python
def create_parent_child_chunks(
    document: dict,
    parent_max_size: int = 1000,
    child_max_size: int = 300
) -> tuple[list[dict], list[dict]]:
    """
    生成父子 chunk
    document: 包含 markdown 和 metadata 的文档
    返回: (parent_chunks, child_chunks)

    parent_chunk:
    {
        "id": str,                          # parent_{doc_hash}_{index}
        "text": str,
        "metadata": {
            # 继承文档元数据 +
            "role": "parent",
            "section_path": str             # 章节路径
        }
    }

    child_chunk:
    {
        "id": str,                          # child_{doc_hash}_{parent_idx}_{child_idx}
        "text": str,
        "metadata": {
            # 继承文档元数据 +
            "role": "child",
            "parent_id": str,               # 指向父 chunk
            "section_path": str
        }
    }
    """
```

---

## 存储 + 检索层（Phase 2）

### retrieval/embedder.py（扩展）

```python
class Embedder:
    def __init__(self, model_name: str): ...
    def embed(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
```

### retrieval/vector_store.py（重构自 store.py）

```python
class VectorStore:
    def __init__(self, chroma_path: str, collection_name: str): ...

    def add_chunks(self, chunks: list[dict], embeddings: list[list[float]]) -> None:
        """写入 chunks 和向量，支持父子 chunk 的 role 和 parent_id 元数据"""

    def query(self, embedding: list[float], top_k: int, where: dict = None) -> list[dict]:
        """向量检索，支持元数据过滤"""

    def get_by_ids(self, ids: list[str]) -> list[dict]:
        """按 ID 批量获取（用于父 chunk 展开）"""

    def get_by_source(self, source: str) -> list[dict]:
        """获取某文件所有 chunks"""

    def count(self) -> int: ...
```

### retrieval/bm25_store.py

```python
class BM25Store:
    def __init__(self, dict_path: str = None): ...

    def build_index(self, chunks: list[dict]) -> None:
        """构建 BM25 索引，jieba 分词"""

    def add_weighted_keywords(self, chunk_id: str, keywords: dict[str, int]) -> None:
        """添加加权关键词（表格 Q&K 用）"""

    def search(self, query: str, top_k: int) -> list[dict]:
        """BM25 检索，返回 [{id, text, score}]"""

    def save(self, path: str) -> None:
        """持久化索引"""

    def load(self, path: str) -> None:
        """加载索引"""
```

### retrieval/hybrid_searcher.py

```python
class HybridSearcher:
    def __init__(self, vector_store, bm25_store, embedder, reranker=None): ...

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict = None,
        use_rerank: bool = True
    ) -> list[dict]:
        """
        完整混合检索流程：
        1. 元数据过滤（如有 filters）
        2. 向量检索 top20 + BM25 top20
        3. RRF 融合 → top10
        4. Reranker 精排 → top_k
        5. 子 chunk → 展开为父 chunk
        返回: [{text, source, title, score, metadata}]
        """
```

### retrieval/reranker.py

```python
class Reranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"): ...

    def rerank(self, query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
        """对候选结果重排序"""
```

### retrieval/parent_resolver.py

```python
class ParentResolver:
    def __init__(self, vector_store): ...

    def resolve(self, child_chunks: list[dict]) -> list[dict]:
        """子 chunk → 通过 parent_id → 获取父 chunk（去重）"""
```

---

## 对话管理层（Phase 3）

### conversation/history.py

```python
class ConversationHistory:
    def __init__(self, max_rounds: int = 10): ...

    def add(self, role: str, content: str) -> None:
        """添加一轮对话"""

    def get_messages(self) -> list[dict]:
        """获取滑动窗口内的历史消息"""

    def clear(self) -> None: ...
```

### conversation/query_rewriter.py

```python
class QueryRewriter:
    def __init__(self, client): ...

    def rewrite(self, query: str, history: list[dict]) -> str:
        """
        结合对话历史改写 query
        例："它的贴息比例是多少" → "中小微企业贷款贴息政策的贴息比例是多少"
        """
```

### conversation/cache.py

```python
class SemanticCache:
    def __init__(self, embedder, db_path: str, max_size: int = 1000,
                 ttl: int = 86400, threshold: float = 0.92): ...

    def get(self, query: str) -> tuple[str, list[str]] | None:
        """查询缓存，返回 (answer, sources) 或 None"""

    def set(self, query: str, answer: str, sources: list[str]) -> None:
        """写入缓存"""

    def invalidate_by_source(self, source: str) -> None:
        """某文档更新时，清除引用该文档的缓存"""
```

---

## Agent 层（Phase 3 优化）

### agent/agent.py

```python
class PolicyAgent:
    def __init__(self, client=None, searcher=None, cache=None,
                 rewriter=None, history=None): ...

    def chat(self, user_message: str, history: list[dict] = None) -> dict:
        """
        处理一轮对话
        返回:
        {
            "answer": str,
            "sources": list[str],
            "from_cache": bool          # 是否来自缓存
        }
        """

    def chat_stream(self, user_message: str, history: list[dict] = None):
        """
        流式版本，yield 文本片段
        最后 yield {"sources": [...], "from_cache": bool}
        """
```

### agent/tools.py（扩展）

```python
TOOL_SCHEMAS = [
    {
        "name": "search_policy",
        "description": "检索政策文档...",
        "input_schema": {
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5},
                "filters": {
                    "type": "object",
                    "properties": {
                        "date_from": {"type": "string"},
                        "date_to": {"type": "string"},
                        "issuing_authority": {"type": "string"},
                        "category": {"type": "string", "enum": [...]},
                    }
                }
            }
        }
    },
    # get_policy_detail 保持不变
    # list_policies 待实现
]
```

---

## Web 层（Phase 3 升级）

### web/app.py

```
GET  /                  → 返回 index.html
POST /api/chat          → 非流式：{ "answer": str, "sources": [...] }
GET  /api/chat/stream   → SSE 流式：逐字返回 + 最终 sources
```

---

## 评估体系（Phase 1 起步，Phase 4 完善）

### evaluation/run_eval.py

```python
def run_evaluation(eval_set_path: str, agent) -> dict:
    """
    一键跑评估
    返回:
    {
        "ragas": {
            "context_precision": float,
            "context_recall": float,
            "faithfulness": float,
            "answer_relevancy": float
        },
        "retrieval": {
            "recall_at_5": float,
            "mrr": float
        },
        "by_category": {
            "融资支持": {...},
            "税收优惠": {...},
            ...
        }
    }
    """
```
