# 目录结构

```
sme-policy-agent/
│
├── data/                          # 原始政策文件（手工下载）
│   ├── *.html
│   └── *.pdf
│
├── src/
│   ├── ingestion/                 # 数据摄入流水线
│   │   ├── loader.py              # HTML/PDF 解析 → 统一文档格式
│   │   ├── chunker.py             # 文本分块
│   │   └── pipeline.py            # 串联 load → chunk → embed → store
│   │
│   ├── retrieval/                 # 检索层
│   │   ├── embedder.py            # 本地 Embedding 模型封装
│   │   └── store.py               # ChromaDB 增删查封装
│   │
│   ├── agent/                     # Agent 核心
│   │   ├── tools.py               # 工具定义与执行（供 Claude tool_use）
│   │   ├── prompts.py             # System prompt
│   │   └── agent.py               # tool_use 多轮主循环
│   │
│   └── web/                       # Flask 应用
│       ├── app.py                 # 路由：GET / 和 POST /api/chat
│       ├── static/
│       │   ├── css/style.css
│       │   └── js/chat.js
│       └── templates/
│           └── index.html
│
├── scripts/
│   └── ingest.py                  # 一次性运行：处理数据写入 ChromaDB
│
├── tests/
│   ├── test_loader.py
│   └── test_retrieval.py
│
├── architecture/                  # 项目上下文文档（AI 编码前必读）
│   ├── overview.md
│   ├── structure.md
│   ├── data_flow.md
│   ├── components.md
│   └── progress.md
│
├── chroma_db/                     # ChromaDB 持久化目录（gitignore）
├── config.py                      # 全局配置
├── .env                           # API Key（gitignore）
├── .env.example                   # 配置模板
├── requirements.txt
└── .gitignore
```
