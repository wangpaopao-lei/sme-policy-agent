# RAG 系统全面升级方案

## 升级目标

将现有的政策问答原型升级为生产级 RAG 系统，重点提升：文档处理质量、检索精度、用户体验、可量化的评估能力。

---

## 整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                         用户交互层                                   │
│  Flask + SSE 流式输出 + 前端 Markdown 渲染                           │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                        对话管理层                                    │
│  多轮对话 History │ Query 改写 │ 语义缓存 │ Memory 管理（后期）       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                        Agent 决策层                                  │
│  Claude Sonnet + System Prompt + Tools                              │
│  自主决定：检索/过滤条件/是否追加检索/直接回答                         │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                         检索层                                      │
│                                                                     │
│  元数据过滤 → 向量检索 ─┐                                           │
│              BM25 ─────┴→ RRF 融合 → Reranker → 父 chunk 展开      │
│                                                                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                         存储层                                      │
│  ChromaDB（向量）│ rank_bm25（关键词）│ SQLite（缓存）               │
└─────────────────────────────────────────────────────────────────────┘



┌─────────────────────────────────────────────────────────────────────┐
│                    离线处理流水线（Ingestion）                        │
│                                                                     │
│  原始文档(PDF/HTML/MD) → 解析+表格提取 → Markdown 标准化(LLM兜底)   │
│  → 元数据增强(正则+LLM) → 语义分块 → 父子chunk → 表格Q&K生成       │
│  → Embedding → 入库(向量+BM25)                                     │
└─────────────────────────────────────────────────────────────────────┘



┌─────────────────────────────────────────────────────────────────────┐
│                         评估体系                                    │
│  RAGAS（标准化评估）│ 自建 LLM-as-Judge（补充）│ 对比实验 │ 持续回归  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 技术选型

### 文档处理层

| 组件 | 选型 | 说明 |
|------|------|------|
| 支持格式 | PDF、HTML、Markdown | 当前阶段不支持 Word/Excel |
| PDF 文本提取 | pdfplumber | 已有，继续使用 |
| PDF 表格提取 | pdfplumber | 提取后转自然语言，LLM 生成 Q&K |
| HTML → Markdown | markdownify + BeautifulSoup | 标签直接映射，自动转换 |
| Markdown | 直接读取 | 标准化格式检查 |
| 元数据提取 | 正则优先 + Haiku 兜底 | 文号/日期/机关用正则，缺失字段用 LLM |
| LLM 兜底模型 | Claude Haiku | 结构整理不需要强推理，成本低 |

### 表格检索增强

表格数据在入库时做额外处理：

```
表格 → 自然语言描述 → LLM 生成：
  - Questions：用于向量检索（和用户问题语义更接近）
  - Keywords：用于 BM25 检索（可按规则分配权重）

存储时一个表格对应：
  - 原始 Markdown 表格（返回给 Claude 阅读）
  - 自然语言描述（embedding 友好）
  - 预生成 Questions（多向量索引）
  - 加权 Keywords（BM25 索引）
```

### 分块层

| 组件 | 选型 | 说明 |
|------|------|------|
| 主策略 | Markdown 标题层级分割 | 文档已是结构化 Markdown，按 H2/H3 切割 |
| 兜底策略 | 固定长度 800字 + 100字 overlap | 单个 section 超长时使用 |
| 父子 chunk | 父 ~1000字（按条）子 ~300字（按款/项） | 子 chunk 检索，父 chunk 送给 Claude |

chunk 大小评测方法：
1. 准备 50 条评估数据集
2. 用不同 chunk 配置重新分块入库
3. 对同一批问题跑 Recall@5 和 MRR
4. 选最优配置

先用经验值启动，评估体系建好后数据驱动调优。

### Embedding + 存储层

| 组件 | 选型 | 说明 |
|------|------|------|
| Embedding 模型 | BGE-M3（本地） | 继续使用，中文能力好，多语言支持 |
| 向量数据库 | ChromaDB | 继续使用，数据量不大够用 |
| BM25 实现 | rank_bm25 + jieba | 轻量，自定义政策领域词典 |
| 中文分词 | jieba + 自定义词典 | 添加政策领域专业词汇 |

### 检索层

| 组件 | 选型 | 说明 |
|------|------|------|
| 混合检索融合 | RRF（k=60） | 不需要调参，鲁棒 |
| Reranker | BGE-Reranker-v2-m3（本地） | 和 BGE-M3 同系列，中文效果好 |
| 粗排数量 | 各 top20 → RRF 融合 top10 | 多召回保证不漏 |
| 精排数量 | Rerank 后 top5 | 精选最相关内容 |
| 元数据过滤 | Claude 通过 Tool 参数传递 | 日期、机关、类别等过滤条件 |

### 对话管理层

| 组件 | 选型 | 说明 |
|------|------|------|
| 对话历史 | 滑动窗口 10 轮 | 保留最近 10 轮对话 |
| Query 改写 | Claude | 多轮对话中解析指代和省略 |
| 缓存 | 语义缓存（SQLite 持久化） | LRU + TTL + source 关联失效 |
| Memory | 暂不实现 | 后期探讨更系统的方法 |

### Agent + Web 层

| 组件 | 选型 | 说明 |
|------|------|------|
| LLM | Claude Sonnet | 继续使用 |
| 最大 Tool 轮数 | 5 | 保持现有 |
| 流式输出 | SSE（Server-Sent Events） | Flask 原生支持，前端用 EventSource |

### 评估体系

| 组件 | 选型 | 说明 |
|------|------|------|
| 主评估框架 | RAGAS | 标准化 RAG 评估：Context Precision/Recall、Faithfulness、Answer Relevancy |
| 补充评估 | 自建 LLM-as-Judge（Haiku） | RAGAS 不覆盖的特定维度 |
| 评估数据集 | LLM 生成 + 人工审核 | 50 条起步，覆盖多种问题类型 |

---

## Phase 划分

### Phase 1：评估基础 + 文档处理升级

**目标：** 建立评估基准线，升级文档处理流水线

```
1.1 评估数据集构建
    - LLM 生成 + 人工审核 50 条问答对
    - 覆盖：简单事实、多条件、跨文档、精确引用、时间相关、无答案

1.2 基准评估
    - 接入 RAGAS，对现有系统跑一轮评估
    - 记录基准指标，作为后续优化的对比基线

1.3 文档解析器升级
    - PDF：pdfplumber 提取文本+表格，LLM(Haiku) 兜底结构整理
    - HTML：markdownify 自动转换
    - Markdown：直接读取，格式标准化
    - 输出：统一的 Markdown 格式（含 YAML frontmatter 元数据）

1.4 元数据增强
    - 正则提取：文号、发布日期、生效/失效日期、发文机关
    - LLM 兜底：正则缺失字段由 Haiku 补充
    - 元数据写入 YAML frontmatter

1.5 表格处理
    - 提取表格，转为 Markdown 表格 + 自然语言描述
    - LLM 生成 Questions 和加权 Keywords（入库用）

交付物：
  - evaluation/dataset/eval_set.json（评估数据集）
  - evaluation/baseline_report.md（基准评估报告）
  - src/ingestion/parsers/（PDF/HTML/MD 解析器）
  - src/ingestion/metadata/（元数据提取器）
  - src/ingestion/table/（表格处理器）
  - data/parsed/（标准化 Markdown 文件）
```

### Phase 2：分块 + 检索升级

**目标：** 语义分块 + 混合检索，核心能力升级

```
2.1 语义分块
    - 基于 Markdown 标题层级的结构化分块
    - 父子 chunk 机制（父按条切 ~1000字，子按款切 ~300字）
    - 固定长度兜底（section 太长时）

2.2 BM25 索引
    - jieba 分词 + 自定义政策词典
    - rank_bm25 建立关键词索引
    - 表格的加权 Keywords 索引

2.3 混合检索
    - 向量检索 top20 + BM25 top20
    - RRF 融合 → top10
    - 元数据过滤（扩展 Tool 参数，Claude 传递过滤条件）

2.4 Reranker
    - BGE-Reranker-v2-m3 本地部署
    - RRF 融合结果 top10 → Rerank → top5
    - 子 chunk 命中 → 展开为父 chunk

2.5 评估验证
    - 用 RAGAS 跑评估，对比 Phase 1 基准线
    - chunk 大小对比实验，数据驱动选最优配置

交付物：
  - src/chunking/（结构化分块 + 父子 chunk）
  - src/retrieval/bm25_store.py（BM25 索引）
  - src/retrieval/hybrid_searcher.py（混合检索 + RRF）
  - src/retrieval/reranker.py（Reranker）
  - src/retrieval/parent_resolver.py（父 chunk 展开）
  - evaluation/phase2_report.md（对比评估报告）
```

### Phase 3：对话体验升级

**目标：** 多轮对话、流式输出、缓存，提升用户体验

```
3.1 流式输出
    - Flask SSE 接口
    - Claude streaming API
    - 前端 EventSource 流式渲染（打字机效果）

3.2 多轮对话
    - 滑动窗口 10 轮历史管理
    - Claude Query 改写（解析指代和省略）

3.3 语义缓存
    - Embedding 相似度匹配缓存
    - LRU + TTL + source 关联失效
    - SQLite 持久化
    - 缓存命中时跳过检索和 Claude 调用

3.4 Agent 策略优化
    - 扩展 Tool 定义（元数据过滤参数、list_policies 等）
    - 优化 System Prompt（few-shot 示例、置信度判断、引用定位）

3.5 评估验证
    - 多轮对话场景的评估用例补充
    - 端到端体验测试

交付物：
  - src/conversation/（历史管理 + Query改写 + 缓存）
  - src/web/ 升级（SSE 流式接口 + 前端流式渲染）
  - src/agent/ 升级（Tool 扩展 + Prompt 优化）
  - evaluation/phase3_report.md（对比评估报告）
```

### Phase 4：评估体系完善 + 整体调优

**目标：** 完善评估闭环，数据驱动全面调优

```
4.1 评估体系完善
    - RAGAS 完整指标：Context Precision/Recall、Faithfulness、Answer Relevancy
    - 自建 LLM-as-Judge 补充维度
    - 按问题类别分析薄弱环节
    - 一键评估脚本

4.2 数据驱动调优
    - chunk 大小对比实验
    - RRF k 值调优
    - Reranker 阈值调优
    - 缓存命中率分析
    - 检索 top_k 参数调优

4.3 评估数据集扩充
    - 从真实用户日志中补充问题
    - 覆盖更多边界场景
    - 目标 100+ 条

交付物：
  - evaluation/ 完整评估工具链
  - 各 Phase 对比报告
  - 最优参数配置文档
```

---

## Phase 里程碑与依赖

```
Phase 1（评估基础 + 文档处理）
    │
    │  评估基准线建立，文档处理就绪
    │
    ▼
Phase 2（分块 + 检索升级）
    │
    │  核心检索能力升级完成，有数据证明提升
    │
    ▼
Phase 3（对话体验升级）
    │
    │  用户可感知的体验提升
    │
    ▼
Phase 4（评估完善 + 调优）
    │
    │  数据驱动的全面优化
    ▼
  后续：Memory 管理、更多文档格式支持、高级 Agent 策略
```

---

## 升级后目录结构

```
sme-policy-agent/
├── data/
│   ├── raw/                        # 原始文件
│   │   ├── pdf/
│   │   ├── html/
│   │   └── markdown/
│   └── parsed/                     # 解析后的标准化 Markdown
│
├── src/
│   ├── ingestion/                  # 文档处理层（Phase 1）
│   │   ├── parsers/
│   │   │   ├── pdf_parser.py       # pdfplumber + LLM 兜底
│   │   │   ├── html_parser.py      # markdownify + BeautifulSoup
│   │   │   └── md_parser.py        # Markdown 标准化
│   │   ├── metadata/
│   │   │   ├── regex_extractor.py  # 正则提取文号/日期/机关
│   │   │   └── llm_extractor.py    # Haiku 兜底提取
│   │   ├── table/
│   │   │   └── table_processor.py  # 表格提取+自然语言+Q&K生成
│   │   ├── cleaner.py              # 格式清洗标准化
│   │   └── pipeline.py             # 串联所有处理步骤
│   │
│   ├── chunking/                   # 分块层（Phase 2）
│   │   ├── structure_splitter.py   # Markdown 标题层级分割
│   │   ├── fixed_splitter.py       # 固定长度兜底分割
│   │   └── parent_child.py         # 父子 chunk 生成与关联
│   │
│   ├── retrieval/                  # 存储+检索层（Phase 2）
│   │   ├── embedder.py             # BGE-M3 封装
│   │   ├── vector_store.py         # ChromaDB 封装
│   │   ├── bm25_store.py           # rank_bm25 + jieba
│   │   ├── index_manager.py        # 双索引同步管理
│   │   ├── hybrid_searcher.py      # 混合检索 + RRF 融合
│   │   ├── reranker.py             # BGE-Reranker-v2-m3
│   │   └── parent_resolver.py      # 子chunk → 父chunk 展开
│   │
│   ├── conversation/               # 对话管理层（Phase 3）
│   │   ├── history.py              # 滑动窗口 10 轮历史
│   │   ├── query_rewriter.py       # Claude Query 改写
│   │   └── cache.py                # 语义缓存（LRU+TTL+source失效）
│   │
│   ├── agent/                      # Agent 层（Phase 3 优化）
│   │   ├── agent.py                # Tool use 主循环
│   │   ├── tools.py                # Tool 定义（含过滤参数）
│   │   └── prompts.py              # System Prompt
│   │
│   └── web/                        # Web 层（Phase 3 升级）
│       ├── app.py                  # Flask + SSE 流式接口
│       ├── static/
│       │   ├── css/style.css
│       │   └── js/chat.js          # 支持流式渲染
│       └── templates/
│           └── index.html
│
├── evaluation/                     # 评估体系（Phase 1 起步，Phase 4 完善）
│   ├── dataset/
│   │   └── eval_set.json           # 评估数据集
│   ├── retrieval_eval.py           # 检索评估（Recall@K, MRR）
│   ├── answer_eval.py              # 回答评估（RAGAS + LLM-as-Judge）
│   ├── report.py                   # 评估报告生成
│   ├── run_eval.py                 # 一键评估脚本
│   └── reports/                    # 各 Phase 评估报告
│       ├── baseline_report.md
│       ├── phase2_report.md
│       ├── phase3_report.md
│       └── phase4_report.md
│
├── scripts/
│   └── ingest.py                   # 摄入入口（适配新流水线）
├── tests/                          # 各模块测试
├── cache/                          # 语义缓存 SQLite 存储
├── config.py                       # 全局配置（扩展新参数）
├── requirements.txt                # 依赖（扩展新库）
└── CLAUDE.md
```
