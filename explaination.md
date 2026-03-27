# 中小企业政策问答 Agent — 项目介绍

## 一、项目背景与目标

国家中小企业政策信息平台发布了大量政策文件，涵盖贷款贴息、设备更新、产业扶持、人才培育等方向。这些文件分散、内容密集，普通用户很难快速找到与自身需求相关的政策条款。

本项目的目标是构建一个**基于 RAG（检索增强生成）的政策问答 Agent**，用户用自然语言提问，系统自动从政策文档库中检索相关内容，由大语言模型（Claude）综合分析后给出准确、有来源依据的回答。

---

## 二、技术选型与理由

| 组件 | 选型 | 理由 |
|------|------|------|
| LLM | Claude API (claude-sonnet-4-6) | 中文理解能力强，支持 tool_use 原生多工具调用 |
| Embedding | BAAI/bge-m3（本地） | 专为多语言设计，中文语义检索效果好，无需外部 API |
| 向量数据库 | ChromaDB | 轻量、本地持久化、零配置，适合演示原型 |
| Web 框架 | Flask + 原生 JS | 无额外框架依赖，代码直观，便于展示逻辑 |
| LLM 框架 | Anthropic SDK（不用 LangChain） | 直接调用，流程透明，调试方便，避免框架黑盒 |

---

## 三、系统架构

系统分为四层，各层职责清晰、互相解耦：

```
┌─────────────────────────────────────────────────┐
│                  Web 层（Flask）                  │
│         GET /   POST /api/chat                   │
└───────────────────────┬─────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────┐
│              Agent 层（PolicyAgent）              │
│   tool_use 多轮循环 · system prompt · 来源收集    │
└──────────┬────────────────────────┬─────────────┘
           │                        │
┌──────────▼──────────┐  ┌──────────▼──────────────┐
│  工具：search_      │  │  工具：get_policy_       │
│  policy()           │  │  detail()               │
└──────────┬──────────┘  └──────────┬──────────────┘
           │                        │
┌──────────▼────────────────────────▼─────────────┐
│          检索层（Embedder + PolicyStore）          │
│      bge-m3 向量化 · ChromaDB cosine 检索         │
└─────────────────────────────────────────────────┘

（数据预处理，离线一次性运行）
┌─────────────────────────────────────────────────┐
│               摄入层（Ingestion）                 │
│   loader → chunker → embedder → ChromaDB        │
└─────────────────────────────────────────────────┘
```

---

## 四、核心流程详解

### 4.1 数据摄入（离线，运行一次）

政策文件（PDF / TXT）经过以下流水线处理后写入向量数据库：

```
原始文件
  → loader.py     解析文本，提取标题和来源信息
  → chunker.py    段落优先分块（约 400 字/块，50 字重叠）
  → embedder.py   bge-m3 本地模型生成语义向量
  → store.py      写入 ChromaDB，支持增量导入（自动跳过已存在）
```

分块策略的考量：块太大会引入无关内容，块太小会丢失上下文。400 字在中文政策场景下约等于一个完整条款，50 字重叠保证条款边界不被切断。

### 4.2 用户问答（在线，每次请求）

```
用户提问
  → Agent 构建 messages，携带两个工具定义发送给 Claude
  → Claude 自主决策：
      ├── 问题无需检索（如问候语）→ 直接回答
      └── 需要政策信息 → 调用 search_policy(query, top_k)
              → bge-m3 向量化查询
              → ChromaDB 返回 top-5 相关片段
              → Claude 读取结果，决定是否继续检索
                  ├── 信息充分 → 生成最终回答
                  └── 需要更多细节 → 调用 get_policy_detail(source)
                          → 获取该文件全文
                          → 生成最终回答（含来源引用）
```

这个循环最多执行 5 轮（MAX_TOOL_ROUNDS），防止异常情况下无限调用。

### 4.3 Agent 能力边界

本项目实现的是**真正的 Agent 模式**：Claude 不是被动地接收检索结果，而是主动决定：

- 是否需要检索
- 用什么关键词检索
- 检索一次够不够，需不需要换词再查
- 是否需要获取某篇文件的完整内容

这与简单的"先检索再生成"流程有本质区别——Claude 是决策者，而不仅仅是输出端。

---

## 五、关键工程决策

### 依赖注入（Dependency Injection）

`PolicyAgent` 的构造函数接受可选的 `client`、`embedder`、`store` 参数：

```python
class PolicyAgent:
    def __init__(self, client=None, embedder=None, store=None):
        ...
```

生产环境不传参数，自动初始化真实依赖；测试时注入 mock 对象，无需启动模型或数据库。这使得所有 Agent 单元测试在毫秒级完成，且不依赖任何外部服务。

### 增量导入

`store.py` 在写入前先检查 chunk ID 是否已存在（基于文件名 + 块序号的 MD5），重复运行 `ingest.py` 不会产生重复数据，方便后续添加新政策文件。

### 单例 Agent

Flask 应用中 `PolicyAgent` 只初始化一次（懒加载单例），避免每次请求都重新加载 bge-m3 模型（约需数秒）。

---

## 六、目录结构

```
sme-policy-agent/
├── data/                   原始政策文件（PDF / TXT）
├── src/
│   ├── ingestion/          数据摄入：loader · chunker · pipeline
│   ├── retrieval/          检索层：embedder · ChromaDB store
│   ├── agent/              Agent 核心：tools · prompts · agent
│   └── web/                Flask 应用 + 前端
├── scripts/ingest.py       一次性数据导入入口
├── tests/                  单元测试 + 集成测试（66 个用例）
├── architecture/           项目文档（供 AI 辅助编码时读取上下文）
└── config.py               全局配置
```

---

## 七、测试策略

测试分两类，采用不同运行方式：

**单元测试**（66 个，无需外部依赖，约 3 秒内完成）

```bash
pytest tests/ -m "not integration"
```

| 测试文件 | 覆盖内容 |
|---------|---------|
| test_loader.py | HTML/PDF/TXT 解析、标题提取、空内容过滤 |
| test_retrieval.py | 分块逻辑、ChromaDB 增删查、ID 去重 |
| test_agent.py | 工具执行、多轮循环、来源收集、历史传递、异常兜底 |
| test_web.py | 路由、参数校验、错误处理、message strip |

**集成测试**（需要真实 Claude API Key + 已导入数据）

```bash
pytest tests/ -m integration
```

覆盖真实问答端到端流程，验证 Claude 能正确调用工具并返回有效答案。

---

## 八、启动与演示

**环境准备**

```bash
conda activate ragagent
cp .env.example .env        # 填入 ANTHROPIC_API_KEY
python scripts/ingest.py    # 导入政策文件（首次运行约需几分钟）
```

**启动服务**

```bash
python src/web/app.py
# 访问 http://localhost:18336
```

**建议演示问题**

| 问题 | 考察点 |
|------|--------|
| 中小微企业贷款贴息政策有哪些条件？ | 单文件精准检索 + 结构化输出 |
| 设备更新贷款和贴息政策有什么区别？ | 多文件对比 + 多轮检索 |
| 优质中小企业梯度培育的申请条件是什么？ | 长文本理解 |
| 人工智能相关的产业政策有哪些？ | 跨文件综合检索 |

---

## 九、可扩展方向

| 方向 | 实现思路 |
|------|---------|
| 实时爬取 | 在 ingestion 层加入定时爬虫，触发增量导入 |
| 流式输出 | Claude API 支持 stream 模式，前端用 SSE 实时渲染回复 |
| 多用户会话 | 将 history 存入 session 或 Redis，支持多用户并发 |
| 更大规模数据 | ChromaDB 替换为 Qdrant 或 pgvector，支持百万级向量 |
| 精度优化 | 检索后加 Cross-Encoder reranker，进一步过滤不相关片段 |
