# 目录结构

```
sme-policy-agent/
│
├── data/
│   ├── raw/                        # 原始文件（手工下载）
│   │   ├── pdf/
│   │   ├── html/
│   │   └── markdown/
│   └── parsed/                     # 解析后的标准化 Markdown（含 YAML frontmatter）
│
├── src/
│   ├── ingestion/                  # 文档处理层（Phase 1）
│   │   ├── parsers/
│   │   │   ├── pdf_parser.py       # pdfplumber 提取文本+表格，LLM(Haiku)兜底
│   │   │   ├── html_parser.py      # markdownify + BeautifulSoup
│   │   │   └── md_parser.py        # Markdown 标准化
│   │   ├── metadata/
│   │   │   ├── regex_extractor.py  # 正则提取文号/日期/机关
│   │   │   └── llm_extractor.py    # Haiku 兜底提取
│   │   ├── table/
│   │   │   └── table_processor.py  # 表格提取 → 自然语言 → Q&K 生成
│   │   ├── cleaner.py              # 格式清洗标准化
│   │   └── pipeline.py             # 串联所有处理步骤
│   │
│   ├── chunking/                   # 分块层（Phase 2）
│   │   ├── structure_splitter.py   # Markdown 标题层级分割（主策略）
│   │   ├── fixed_splitter.py       # 固定长度兜底分割
│   │   └── parent_child.py         # 父子 chunk 生成与关联
│   │
│   ├── retrieval/                  # 存储+检索层（Phase 2）
│   │   ├── embedder.py             # BGE-M3 Embedding 封装
│   │   ├── vector_store.py         # ChromaDB 封装（重构自 store.py）
│   │   ├── bm25_store.py           # rank_bm25 + jieba 分词
│   │   ├── index_manager.py        # 双索引同步管理
│   │   ├── hybrid_searcher.py      # 混合检索 + RRF 融合
│   │   ├── reranker.py             # BGE-Reranker-v2-m3
│   │   └── parent_resolver.py      # 子chunk → 父chunk 展开
│   │
│   ├── conversation/               # 对话管理层（Phase 3）
│   │   ├── history.py              # 滑动窗口 10 轮历史管理
│   │   ├── query_rewriter.py       # Claude Query 改写
│   │   └── cache.py                # 语义缓存（LRU+TTL+source失效）
│   │
│   ├── agent/                      # Agent 层（Phase 3 优化）
│   │   ├── agent.py                # Tool use 主循环 + 流式支持
│   │   ├── tools.py                # Tool 定义（含 filters 参数）
│   │   └── prompts.py              # System Prompt（含 few-shot）
│   │
│   └── web/                        # Web 层（Phase 3 升级）
│       ├── app.py                  # Flask + SSE 流式接口
│       ├── static/
│       │   ├── css/style.css
│       │   └── js/chat.js          # 支持 EventSource 流式渲染
│       └── templates/
│           └── index.html
│
├── evaluation/                     # 评估体系（Phase 1 起步，Phase 4 完善）
│   ├── dataset/
│   │   └── eval_set.json           # 评估数据集（50条起步）
│   ├── retrieval_eval.py           # 检索评估（Recall@K, MRR）
│   ├── answer_eval.py              # 回答评估（RAGAS + LLM-as-Judge）
│   ├── report.py                   # 评估报告生成
│   ├── run_eval.py                 # 一键评估脚本
│   └── reports/                    # 各 Phase 评估报告
│
├── scripts/
│   └── ingest.py                   # 摄入入口（适配新流水线）
│
├── tests/                          # 各模块单元测试+集成测试
│   ├── test_loader.py              # 原有（Phase 1 重构）
│   ├── test_retrieval.py           # 原有（Phase 2 扩展）
│   ├── test_agent.py               # 原有（Phase 3 扩展）
│   ├── test_web.py                 # 原有（Phase 3 扩展）
│   ├── test_parsers.py             # Phase 1 新增
│   ├── test_metadata.py            # Phase 1 新增
│   ├── test_chunking.py            # Phase 2 新增
│   ├── test_bm25.py                # Phase 2 新增
│   ├── test_hybrid_search.py       # Phase 2 新增
│   ├── test_cache.py               # Phase 3 新增
│   └── test_query_rewriter.py      # Phase 3 新增
│
├── cache/                          # 语义缓存 SQLite 存储
├── chroma_db/                      # ChromaDB 持久化目录（gitignore）
│
├── architecture/                   # 项目架构文档
│   ├── overview.md                 # 项目概览+技术选型
│   ├── structure.md                # 目录结构（本文件）
│   ├── data_flow.md                # 数据流图
│   ├── components.md               # 模块接口约定
│   ├── upgrade_plan.md             # 升级方案+Phase划分
│   └── progress.md                 # 开发进度
│
├── config.py                       # 全局配置
├── .env / .env.example             # API Key
├── requirements.txt                # Python 依赖
├── CLAUDE.md                       # AI 编码指令
└── .gitignore
```
