# 详细设计文档

## 1. 文档处理层

### 1.1 解析器（src/ingestion/parsers/）

三种解析器统一输出格式：

```python
{
    "markdown": str,       # 结构化 Markdown
    "tables": list[dict],  # 提取的表格 [{"markdown": str, "page": int}]
    "raw_text": str,       # 原始文本（用于元数据提取）
    "source": str,         # 文件名
    "title": str,          # 文档标题
    "file_type": str,      # "pdf" | "html" | "markdown"
}
```

**PDF 解析器**
- pdfplumber 逐页提取文本和表格
- 结构识别：正则匹配"第X章"→H2、"第X条"→H3、"一、"→H4、"（一）"→列表项、"1."→子列表项
- 表格处理：多列→Markdown 表格，单列（专栏类）→引用块
- 页码行自动过滤
- 预留了 `_is_header_by_font` 字号检测函数（未启用，备选方案）

**HTML 解析器**
- markdownify 做 HTML→Markdown 转换
- 噪音清理：移除 script/style/nav/footer/header/aside/iframe 标签和图片
- 布局表格检测：有 th→数据表，单元格>200字→布局表，布局表提取文本不保留格式
- meta 标签提取：title、publish_date、author、keywords
- 网站噪音正则过滤（导航栏、登录注册等 18 种模式）

**Markdown/TXT 解析器**
- TXT 文件按 Markdown 格式处理（数据来源的 TXT 实际是网页抓取的 Markdown）
- 噪音正则过滤（和 HTML 解析器共用模式 + 额外 4 种 Markdown 特有模式）
- 粗体标题转换：`**一、政策内容**` → `#### 一、政策内容`
- 发布来源提取：`发布来源:财政部` → meta_tags

### 1.2 元数据提取（src/ingestion/metadata/）

**两级提取策略：正则优先，LLM 兜底**

正则提取器覆盖的字段和策略：
| 字段 | 策略 | 搜索范围 |
|------|------|---------|
| policy_number | `XX〔YYYY〕N号` 模式 | 前 500 字 |
| issuing_authority | 从文号前缀匹配→已知机关列表匹配→"发布来源"行提取 | 前 500 字 |
| publish_date | 取文末最后一个日期（落款处） | 后 500 字，fallback 前 500 字 |
| effective_date | "自X日起施行/执行/实施" | 全文 |
| expiry_date | "有效期至X" | 全文 |
| applicable_region | "各省、自治区"→全国 | 前 500 字 |
| category | 关键词计数分类（5 类 x 7 关键词） | 标题 + 前 1000 字 |

已知机关列表：32 个（国务院系列、各部委、金融机构）。

LLM 提取器：仅对重要字段（title、policy_number、issuing_authority、publish_date、category）的缺失值调用 Haiku，成本可控。

**元数据合并优先级：** parser_meta > regex_meta > llm_meta

### 1.3 表格处理器（src/ingestion/table/）

表格检索增强流程：
```
表格 Markdown → 自然语言描述 → LLM 生成 Questions + Keywords
```

- 多列表格：逐行转"字段为值"句式，如"企业类型为小型企业，贴息比例为2%，最高额度为500万"
- 单列表格（专栏）：去引用标记保留原文
- LLM 生成：Questions（3-5 个口语化问题）用于向量检索，Keywords（<=15 个加权词）用于 BM25
- Keywords 权重规则：核心概念=5，关键数据=4，实体=3，一般词=2
- 章节上下文提取：从全文中找表格前最近的标题，提升 Q&K 质量

### 1.4 清洗与输出（src/ingestion/cleaner.py + pipeline_v2.py）

**cleaner** 做最终格式清洗：全角空格→半角、行尾空格、多余空行压缩、YAML frontmatter 生成（字段按固定顺序、含冒号的值自动加引号）。

**pipeline_v2** 串联完整流程：
```
扫描文件 → 按后缀分发到 parser → 正则元数据 → LLM 兜底 → 合并元数据
→ 表格处理（如有表格且开启 LLM）→ cleaner 清洗 → 输出 data/parsed/*.md
```

`use_llm` 开关控制是否调用 LLM（元数据兜底 + 表格 Q&K），方便无 API key 时跳过。

---

## 2. 分块层

### 2.1 结构化分块（src/chunking/structure_splitter.py）

**自动检测切割层级：**
- 跳过 H1（文档标题）
- H3 >= 3 个 → 按 H3 切（章+条结构，如管理办法）
- H4 >= 2 个 → 按 H4 切（节结构，如通知/意见）
- H2 >= 2 个 → 按 H2 切
- 否则取最多的层级

切割时保留父标题：如 H2"第一章 总则"下的 H3"第一条"，section_path 为"第一章 总则 > 第一条"。

自动跳过 YAML frontmatter。

### 2.2 固定长度分块（src/chunking/fixed_splitter.py）

兜底策略，在 section 超长时使用：
- 按段落边界切割（不在段落中间切）
- 从后往前取段落构建 overlap
- 默认 800 字 + 100 字 overlap

### 2.3 父子 chunk（src/chunking/parent_child.py）

```
文档 → structure_splitter → sections（候选父 chunk）
  每个 section → 超长则 fixed_split → 父 chunk 列表
    每个父 chunk → _split_into_sub_sections → 子 chunk 列表
```

子 chunk 切割优先按子项结构（（一）（二）、1.2.3.），无子项则用 fixed_split。

ID 生成：`md5(source::role::p_idx::pp_idx[::c_idx])`，确定性、可重现。

子 chunk metadata 含 `parent_id` 指向父 chunk，检索命中后可展开。

---

## 3. 存储 + 检索层

### 3.1 向量存储（src/retrieval/vector_store.py）

ChromaDB 封装，相比 v1 store.py 新增：
- 支持任意 metadata（role、parent_id、category、publish_date 等）
- `add_chunks_without_embeddings()`：父 chunk 不做 embedding，只用于展开阅读
- `query()` 支持 `where` 过滤
- `get_by_ids()` 批量查询（父 chunk 展开用）
- metadata 值自动过滤为 ChromaDB 支持的类型（str/int/float/bool）

### 3.2 BM25 索引（src/retrieval/bm25_store.py）

- rank_bm25 + jieba 分词
- 30+ 自定义政策词典（中小微企业、专精特新、贷款贴息等）
- 分词预处理：去 Markdown 标记、过滤单字符/纯数字/纯标点
- 加权关键词：通过重复 token N 次实现权重效果
- pickle 持久化

### 3.3 混合检索（src/retrieval/hybrid_searcher.py）

完整流程：
```
query → embedding
  ↓
元数据过滤（where 条件 + role="child"）
  ↓
向量检索 top20 + BM25 top20
  ↓
RRF 融合 top10（k=60，不看分数只看排名）
  ↓
Reranker top5（可选）
  ↓
子 chunk → parent_id → 父 chunk 展开（去重）
```

RRF 公式：`score(d) = Σ 1/(k + rank_i)`，两路的 rank 独立叠加。

父 chunk 展开：收集所有命中子 chunk 的 parent_id，去重后 `get_by_ids()`，按原始 rrf_score 排序。

元数据过滤：从 filters 构建 ChromaDB where 条件，支持 date_from/date_to/issuing_authority/category，自动附加 `role="child"`。

### 3.4 Reranker（src/retrieval/reranker.py）

CrossEncoder 封装（默认 BGE-Reranker-v2-m3），lazy import 避免在测试中加载 PyTorch。输入 query-document 对，输出按 rerank_score 排序的结果。

---

## 4. 对话管理层

### 4.1 对话历史（src/conversation/history.py）

滑动窗口（默认 10 轮 = 20 条消息），裁剪后确保第一条是 user（Claude API 要求）。

`get_recent_context(n_rounds)` 生成"用户: xxx\n助手: xxx"格式的文本，供 query rewriter 使用。消息超 200 字自动截断。

### 4.2 Query 改写（src/conversation/query_rewriter.py）

启发式判断是否需要改写：
- 包含指代词（它、这个、该、那个等 13 个）→ 需要
- 问题 < 10 字 → 需要
- 无历史上下文 → 不需要
- 不包含指代词且 >= 10 字 → 不需要（省 API 调用）

用 Haiku 改写，安全检查：结果 < 2 字或 > 原文 5 倍长度则放弃改写。LLM 调用失败时 fallback 到原 query。

### 4.3 语义缓存（src/conversation/cache.py）

**命中逻辑：**
1. query → embedding
2. 遍历缓存，跳过 TTL 过期的
3. 计算余弦相似度，取最高分
4. 超过阈值（0.92）→ 命中，更新 LRU 顺序

**写入逻辑：**
1. LRU 满时淘汰 OrderedDict 最前面（最久未访问）的
2. 存入 query + embedding + answer + sources + timestamp

**失效逻辑：**
- TTL：get() 时检查 timestamp，过期自动删除
- LRU：set() 时检查 count >= max_size，淘汰最旧
- Source：`invalidate_by_source(source)` 遍历缓存，删除 sources 包含该 source 的条目

**持久化：** SQLite 存储 embedding（BLOB）、answer、sources（JSON）、timestamp、last_accessed。启动时加载到内存 OrderedDict。

---

## 5. Agent + Web 层

### 5.1 Agent（src/agent/agent.py）

**chat()** — 非流式，保持不变。tool_use 多轮循环，最多 5 轮。

**chat_stream()** — 流式生成器：
```python
for round in range(MAX_TOOL_ROUNDS):
    response = client.messages.create(...)  # 非流式
    if tool_use → 执行工具，继续
    if end_turn → break

# 最后用 client.messages.stream() 流式输出最终文本
with client.messages.stream(...) as stream:
    for text in stream.text_stream:
        yield {"type": "text", "text": text}
yield {"type": "done", "sources": [...]}
```

设计决策：tool_use 阶段不流式（Claude 在思考和调用工具，没有文本输出），最终回答阶段流式（用户看到逐字输出）。

### 5.2 Tools（src/agent/tools.py）

search_policy 的 filters 参数：
```json
{
    "date_from": "YYYY-MM-DD",
    "date_to": "YYYY-MM-DD",
    "issuing_authority": "机关名",
    "category": "融资支持|税收优惠|人才政策|产业扶持|科技创新"
}
```

Claude 根据用户问题自动判断是否传 filters。目前 filters 传递到 execute_search_policy 但尚未接入 hybrid_searcher（v1 store 不支持），Phase 4 整合后生效。

### 5.3 Prompts（src/agent/prompts.py）

System Prompt 结构：
1. 角色定义
2. 工具能力说明
3. 回答原则（6 条）
4. **检索策略 few-shot 示例**（3 个场景：单查询、带过滤、对比查询）
5. **置信度判断引导**
6. 回答格式要求
7. 范围限制

### 5.4 Web（src/web/app.py）

两个端点并存：
- `POST /api/chat` — 非流式，返回 JSON（向后兼容）
- `POST /api/chat/stream` — SSE 流式，返回 `text/event-stream`

SSE 事件格式：
```
data: {"type": "text", "text": "..."}     ← 文本片段
data: {"type": "done", "sources": [...]}  ← 完成
data: {"type": "error", "message": "..."} ← 错误
```

### 5.5 前端（src/web/static/js/chat.js）

使用 `fetch()` + `ReadableStream` 手动解析 SSE（非 EventSource，因为需要 POST）。

流式渲染：每收到 text 事件就拼接全文并 `marked.parse()` 重新渲染 Markdown。done 事件时追加 source 标签。去掉了原来的三点加载动画。

---

## 6. 评估体系

### 6.1 评估数据集（evaluation/dataset/eval_set.json）

50 条 QA 对，全部基于真实文档内容手工编写。

| 类型 | 数量 | 说明 |
|------|------|------|
| 简单事实 | 28 | 单一文档中的具体数据 |
| 跨文档 | 4 | 需要综合多篇文档 |
| 否定问题 | 4 | "不能""不适用"类 |
| 多条件 | 3 | 用户给出自身条件求匹配 |
| 精确引用 | 3 | 文号、网址等精确匹配 |
| 时间相关 | 3 | "今年""有效期" |
| 无答案 | 3 | 文档库中没有的信息 |
| 模糊口语 | 2 | "有啥补贴能拿" |

覆盖 16 篇文档、5 个政策类别。

### 6.2 检索评估（evaluation/retrieval_eval.py）

- Recall@K：top-k 中是否包含正确文档
- MRR：正确文档排在第几位
- 引号归一化：全角/半角/日文引号统一为 ASCII 引号后比较
- 按 category 分组统计 + 失败案例收集

### 6.3 回答评估（evaluation/answer_eval.py）

**RAGAS**：接入 Faithfulness、Response Relevancy、Context Precision/Recall，用 Claude 作为评估 LLM。

**LLM-as-Judge**：自建 Haiku 评估，4 个维度（忠实度/相关性/完整性/正确性），1-5 分。

### 6.4 一键评估（evaluation/run_eval.py）

三种模式：
- `python run_eval.py` — 纯检索评估（快速，不调 LLM）
- `python run_eval.py --judge` — 检索 + LLM-as-Judge
- `python run_eval.py --full` — 完整评估（检索 + RAGAS + Judge）

输出 JSON 报告到 `evaluation/reports/`。

### 6.5 基准评估结果

v1 pipeline（纯向量检索，400 字固定分块）：
- Recall@5 = 0.98
- MRR = 0.922
- 真实失败 1 个："中药工业"被偏向相似产业文档（BM25 上线后可修复）

---

## 7. 模块整合（Phase 4 完成）

### 7.1 v2 摄入脚本（scripts/ingest_v2.py）

完整 5 步流程：
```
步骤 1: 文档解析（pipeline_v2: parse → metadata → table Q&K）
步骤 2: 父子分块（create_parent_child_chunks）
步骤 3: 子 chunk Embedding（BGE-M3 批量）
步骤 4: 写入 ChromaDB（父 chunk 无 embedding，子 chunk 有 embedding）
步骤 5: 构建 BM25 索引（子 chunk + 表格加权关键词注入）
```

CLI 参数：`--no-llm`（跳过 LLM）、`--clean`（清空重建）。

collection 命名：v2 使用 `sme_policies_v2`，和 v1 的 `sme_policies` 共存。

### 7.2 Agent 整合

PolicyAgent 构造函数新增可选参数：
- `searcher`：HybridSearcher（v2 模式）
- `history_manager`：ConversationHistory
- `query_rewriter`：QueryRewriter
- `cache`：SemanticCache

完整 v2 对话流程：
```
用户提问 → 缓存检查 → 命中则直接返回
         → 未命中 → query 改写 → 对话历史管理
         → tool_use 循环（search_policy 使用 HybridSearcher）
         → 回答生成 → 写入缓存 + 更新历史
```

向后兼容：不传 v2 组件时，自动 fallback 到 v1 的 PolicyStore。

### 7.3 Tools 整合

`execute_search_policy` 优先使用 `searcher`（HybridSearcher），fallback 到 `store`（PolicyStore）。v2 chunk 格式的 metadata 提取（source 在 metadata 中，score 取 rrf_score/rerank_score）。

`execute_tool` 新增 `searcher` 参数透传。

### 7.4 Web 整合

会话管理：内存 dict 存储 `session_id → ConversationHistory`。

新增 `/api/session/clear` 端点。

### 7.5 参数调优框架（evaluation/tuning.py）

CLI 扫描实验：
```bash
python evaluation/tuning.py --param rrf_k --values 20,40,60,80,100
python evaluation/tuning.py --param top_k --values 3,5,7,10
python evaluation/tuning.py --param use_rerank --values true,false
```

每组参数运行完整检索评估，输出对比表格（Recall@K、MRR、耗时、失败数），自动标记最优值，保存 JSON 报告。

**实验结论：**

| 参数 | 测试范围 | 最优值 | 结论 |
|------|---------|--------|------|
| rrf_k | 20-100 | 60（默认） | 无差异，当前数据规模下两路排名高度一致 |
| top_k | 3-10 | 7 | 线性提升：3→0.94, 5→0.96, 7→0.97, 10→0.98 |
| rerank | true/false | false | +1% Recall 但 11x 慢（64s vs 5.7s），性价比低 |

### 7.6 评估数据集

从 50 条扩充到 105 条：

| 类别 | 数量 |
|------|------|
| 简单事实 | 52 |
| 模糊口语 | 9 |
| 多条件 | 8 |
| 跨文档 | 8 |
| 否定问题 | 8 |
| 时间相关 | 7 |
| 无答案 | 7 |
| 精确引用 | 6 |

所有 16 篇文档每篇至少 3 个问题，5 个政策类别均有覆盖。
