# 项目概览

## 项目目标
面向国家中小企业政策信息平台的问答 Agent。用户可通过 Web 界面提问，Agent 自主决定检索策略，从政策文档库中找到相关信息并作答。系统具备混合检索、语义缓存、流式输出、多轮对话等能力，并通过 RAGAS 评估体系持续优化。

## 技术栈

### 文档处理层
| 组件 | 选型 | 说明 |
|------|------|------|
| PDF 文本提取 | pdfplumber | 继续使用，复杂文档 LLM(Haiku) 兜底 |
| PDF 表格提取 | pdfplumber | 提取后转自然语言，LLM 生成 Questions & Keywords |
| HTML 转 Markdown | markdownify + BeautifulSoup4 | 标签自动映射 |
| Markdown | 直接读取 | 格式标准化 |
| 元数据提取 | 正则 + Haiku 兜底 | 文号/日期/机关/类别 |

### 分块层
| 组件 | 选型 | 说明 |
|------|------|------|
| 主策略 | Markdown 标题层级分割 | 按 H2/H3 结构切割 |
| 兜底 | 固定长度 800字 + 100字 overlap | section 超长时使用 |
| 父子 chunk | 父 ~1000字 / 子 ~300字 | 子 chunk 检索，父 chunk 送 Claude |

### 检索层
| 组件 | 选型 | 说明 |
|------|------|------|
| Embedding | BAAI/bge-m3 | 本地模型，中文多语言支持 |
| 向量数据库 | ChromaDB | 本地持久化 |
| BM25 | rank_bm25 + jieba | 自定义政策领域词典 |
| 混合检索融合 | RRF（k=60） | 向量top20 + BM25top20 → 融合top10 |
| Reranker | BGE-Reranker-v2-m3 | 本地部署，融合top10 → 精排top5 |
| 元数据过滤 | Claude Tool 参数 | 日期/机关/类别过滤 |

### 对话管理层
| 组件 | 选型 | 说明 |
|------|------|------|
| 对话历史 | 滑动窗口 10 轮 | |
| Query 改写 | Claude | 多轮对话中解析指代和省略 |
| 语义缓存 | SQLite 持久化 | LRU + TTL + source 关联失效 |

### Agent + Web 层
| 组件 | 选型 | 说明 |
|------|------|------|
| LLM | Claude Sonnet (claude-sonnet-4-6) | Anthropic SDK |
| Web 框架 | Flask + SSE + 原生 JS | 流式输出 |
| 最大 Tool 轮数 | 5 | |

### 评估体系
| 组件 | 选型 | 说明 |
|------|------|------|
| 主框架 | RAGAS | Context Precision/Recall, Faithfulness, Answer Relevancy |
| 补充 | 自建 LLM-as-Judge (Haiku) | 特定维度补充评估 |
| 数据集 | LLM 生成 + 人工审核 | 50 条起步，目标 100+ |

## 数据来源
手工下载的政策文件，位于 `data/raw/` 目录，支持 PDF、HTML、Markdown 三种格式。

## Agent 能力
Claude 自主决定是否检索、检索几次、使用什么过滤条件，通过 tool_use 多轮循环实现。
工具清单：
- `search_policy(query, top_k, filters)` — 混合检索相关政策片段（向量+BM25+元数据过滤）
- `get_policy_detail(source)` — 获取某篇政策的完整内容
- `list_policies()` — 列出所有可用政策文档（待实现）

## 关键约束
- 数据为静态导入，不需要实时爬取
- 写代码前先告知方案，批准后再动手
- 每次写完代码后更新 architecture 目录
- 新增代码后需要添加单元测试或集成测试

## 升级计划
详见 [upgrade_plan.md](upgrade_plan.md)，分 4 个 Phase 实施。
