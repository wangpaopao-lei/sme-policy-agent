# 数据流

## 一次性摄入流程（运行 scripts/ingest.py）

```
data/*.html / data/*.pdf
    │
    ▼ loader.py
    Document {
        text: str,          # 纯文本内容
        source: str,        # 文件名
        title: str,         # 文档标题
        file_type: str      # "html" | "pdf"
    }
    │
    ▼ chunker.py
    Chunk {
        text: str,          # 分块文本（约 400 字）
        source: str,        # 来源文件名
        title: str,         # 文档标题
        chunk_index: int    # 块序号
    }
    │
    ▼ embedder.py
    vector: List[float]     # bge-m3 生成的向量
    │
    ▼ store.py (ChromaDB)
    持久化到 chroma_db/
```

## 用户问答流程

```
用户输入
    │
    ▼ agent.py
    构建 messages + tools 定义，调用 Claude API
    │
    ▼ Claude 决策
    ├── 直接回答（无需检索）→ 返回结果
    └── 调用工具
          │
          ├── search_policy(query, top_k)
          │       ▼ embedder.py → store.py
          │       返回 top-k chunks + source + score
          │
          └── get_policy_detail(source)
                  ▼ store.py 查询该文件所有 chunks
                  返回完整摘要
    │
    ▼ 工具结果塞回 messages，继续调用 Claude
    │（可多轮，直到 stop_reason == "end_turn"）
    │
    ▼ 最终回复 + 来源引用列表
    │
    ▼ Flask POST /api/chat 返回 JSON
    │
    ▼ 前端渲染聊天气泡
```
