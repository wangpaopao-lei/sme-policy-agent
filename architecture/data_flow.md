# 数据流

## 离线摄入流程（scripts/ingest.py）

```
data/raw/ (PDF / HTML / Markdown)
    │
    ▼ parsers/ (pdf_parser / html_parser / md_parser)
    │
    │  PDF: pdfplumber 提取文本+表格，复杂格式 Haiku 兜底
    │  HTML: markdownify 自动转换
    │  MD: 直接读取，格式标准化
    │
    ▼ 统一的 Markdown + 原始表格数据
    │
    ├──▶ metadata/ (regex_extractor → llm_extractor 兜底)
    │    提取：文号、发布日期、发文机关、类别、适用地区
    │    写入 YAML frontmatter
    │
    ├──▶ table/ (table_processor)
    │    表格 → 自然语言描述
    │    → LLM 生成 Questions (向量检索用)
    │    → LLM 生成加权 Keywords (BM25用)
    │
    ▼ data/parsed/*.md (标准化 Markdown + 元数据)
    │
    ▼ chunking/
    │
    │  structure_splitter: 按 Markdown 标题层级切割
    │  → 超长 section: fixed_splitter 兜底 (800字+100重叠)
    │  → parent_child: 生成父子 chunk
    │
    │  父 chunk (~1000字，按条切):
    │    用于送给 Claude 阅读，提供完整上下文
    │  子 chunk (~300字，按款切):
    │    用于检索命中，粒度细精度高
    │
    ▼ Embedding (BGE-M3)
    │
    │  子 chunk → embedding → 向量索引
    │  表格 Questions → embedding → 向量索引
    │
    ├──▶ ChromaDB (向量存储)
    │    子 chunk + embedding + metadata (含 parent_id, role)
    │    父 chunk + metadata (role="parent", 不做 embedding)
    │
    └──▶ rank_bm25 (关键词索引)
         子 chunk → jieba 分词 → BM25 索引
         表格 Keywords → 加权写入 BM25 索引
```

## 在线问答流程

```
用户输入
    │
    ▼ conversation/history.py
    │  维护滑动窗口（最近10轮）
    │
    ▼ conversation/query_rewriter.py
    │  结合历史改写 query
    │  "它的贴息比例" → "中小微企业贷款贴息政策的贴息比例"
    │
    ▼ conversation/cache.py
    │  语义缓存查找（embedding 相似度 > 0.92）
    │
    ├── 缓存命中 → 直接返回 answer + sources
    │
    └── 缓存未命中 ↓
    │
    ▼ agent/agent.py
    │  构建 messages + tools 定义，调用 Claude API (Streaming)
    │
    ▼ Claude 决策
    ├── 直接回答（无需检索）→ 流式返回
    └── 调用工具 ↓
          │
          ├── search_policy(query, top_k, filters)
          │       │
          │       ▼ retrieval/hybrid_searcher.py
          │       │
          │       ├─ filters 非空？→ 元数据过滤（缩小候选集）
          │       │
          │       ├─ 向量检索 top20 (ChromaDB, 只搜子chunk)
          │       ├─ BM25 检索 top20 (rank_bm25)
          │       │
          │       ▼ RRF 融合 → top10
          │       │
          │       ▼ reranker.py (BGE-Reranker-v2-m3) → top5
          │       │
          │       ▼ parent_resolver.py
          │       │  子 chunk → parent_id → 获取父 chunk（去重）
          │       │
          │       ▼ 返回父 chunk 列表 + source + score
          │
          └── get_policy_detail(source)
                  ▼ vector_store.get_by_source(source)
                  返回完整文档内容
    │
    ▼ 工具结果塞回 messages，继续调用 Claude (可多轮，max 5轮)
    │
    ▼ 最终回复 (流式) + 来源引用列表
    │
    ├──▶ 写入语义缓存 (query embedding + answer + sources)
    │
    ▼ Flask SSE → 前端 EventSource 流式渲染
```

## 缓存失效流程

```
文档库更新（重新运行 ingest.py）
    │
    ▼ 识别更新了哪些 source 文件
    │
    ▼ cache.invalidate_by_source(source)
    │  只清除引用了被更新文档的缓存条目
    │
    ▼ 未被引用的缓存条目保留
    │
    另外：
    ├── TTL 过期（24小时）→ 自动淘汰
    └── LRU 满（1000条）→ 淘汰最久未访问的
```

## 评估流程

```
evaluation/dataset/eval_set.json (问答对 + 标准答案)
    │
    ▼ evaluation/run_eval.py
    │
    ├── 对每个问题运行 Agent → 获取 answer + contexts + sources
    │
    ├── 检索评估
    │   ├── Recall@5: 正确文档是否在 top5 中
    │   └── MRR: 正确文档的排名
    │
    ├── RAGAS 评估
    │   ├── Context Precision: 检索结果中多少是相关的
    │   ├── Context Recall: 相关信息被检索到了多少
    │   ├── Faithfulness: 回答是否忠于检索内容
    │   └── Answer Relevancy: 回答是否回答了问题
    │
    └── 生成评估报告
        ├── 总体指标
        ├── 按类别分析
        └── 失败案例分析
```
