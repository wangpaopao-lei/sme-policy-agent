# 中小企业政策问答 Agent
### SME Policy Q&A Agent

> 基于 RAG + Claude API 的中小企业政策智能问答系统
> An intelligent Q&A system for SME policies, built with RAG and Claude API

---

## 简介 | Overview

**中文**

本项目是一个面向国家中小企业政策信息平台的问答 Agent 原型。用户通过自然语言提问，系统自动检索政策文档库，由 Claude 大语言模型综合分析后给出有来源依据的结构化回答。

**English**

This project is a Q&A Agent prototype for China's National SME Policy Information Platform. Users ask questions in natural language; the system retrieves relevant policy documents and uses Claude to generate structured, source-cited answers.

---

## 技术栈 | Tech Stack

| 组件 Component | 选型 Choice | 说明 Note |
|---|---|---|
| LLM | Claude API (claude-sonnet-4-6) | Anthropic SDK，tool_use 多轮调用 |
| Embedding | BAAI/bge-m3 | 本地模型，中文语义检索 / Local model, Chinese semantic search |
| 向量数据库 Vector DB | ChromaDB | 本地持久化 / Local persistent storage |
| Web 框架 Web Framework | Flask + Vanilla JS | 轻量前端 / Lightweight frontend |
| 文档解析 Doc Parsing | pdfplumber + BeautifulSoup4 | PDF & HTML & TXT |

---

## 系统架构 | Architecture

```
┌──────────────────────────────────────────┐
│            Web Layer (Flask)             │
│        GET /    POST /api/chat           │
└─────────────────┬────────────────────────┘
                  │
┌─────────────────▼────────────────────────┐
│         Agent Layer (PolicyAgent)        │
│  tool_use loop · system prompt · sources │
└────────┬─────────────────────┬───────────┘
         │                     │
   search_policy()     get_policy_detail()
         │                     │
┌────────▼─────────────────────▼───────────┐
│      Retrieval Layer (Embedder + Store)  │
│     bge-m3 vectors · ChromaDB cosine     │
└──────────────────────────────────────────┘

  [Offline / 离线]
┌──────────────────────────────────────────┐
│         Ingestion Pipeline               │
│  loader → chunker → embedder → ChromaDB  │
└──────────────────────────────────────────┘
```

---

## 核心特性 | Key Features

- **真正的 Agent 模式 / True Agent Pattern**：Claude 自主决定是否检索、检索几次、用什么关键词，而非固定的"检索→生成"流水线
- **多轮工具调用 / Multi-turn Tool Use**：支持最多 5 轮 tool_use 循环，复杂问题可多次检索后综合回答
- **来源引用 / Source Citation**：每条回答附带政策文件来源，可追溯
- **增量导入 / Incremental Ingestion**：基于 MD5 的 chunk ID，重复运行不产生重复数据
- **依赖注入 / Dependency Injection**：Agent 支持 mock 注入，单元测试无需真实模型或数据库

---

## 快速开始 | Quick Start

### 1. 环境准备 | Setup

```bash
conda create -n ragagent python=3.11 -y
conda activate ragagent
pip install -r requirements.txt
```

### 2. 配置 | Configuration

```bash
cp .env.example .env
# 编辑 .env，填入 ANTHROPIC_API_KEY
```

### 3. 导入数据 | Ingest Data

将政策文件（PDF / TXT）放入 `data/` 目录，然后运行：

```bash
python scripts/ingest.py
```

### 4. 启动服务 | Start Server

```bash
python src/web/app.py
# 访问 / Visit: http://localhost:18336
```

---

## 测试 | Testing

```bash
# 单元测试（无需外部依赖）/ Unit tests (no external deps)
pytest tests/ -m "not integration"

# 集成测试（需要 API Key + 已导入数据）/ Integration tests (requires API key + data)
pytest tests/ -m integration
```

当前单元测试：**66 个用例，全部通过** / Current unit tests: **66 cases, all passing**

---

## 项目结构 | Project Structure

```
sme-policy-agent/
├── data/                   政策文件 / Policy documents
├── src/
│   ├── ingestion/          数据摄入 / Data ingestion
│   │   ├── loader.py       文档解析 / Document parsing
│   │   ├── chunker.py      文本分块 / Text chunking
│   │   └── pipeline.py     摄入流水线 / Ingestion pipeline
│   ├── retrieval/          检索层 / Retrieval layer
│   │   ├── embedder.py     向量化 / Embedding
│   │   └── store.py        ChromaDB 封装 / ChromaDB wrapper
│   ├── agent/              Agent 核心 / Agent core
│   │   ├── agent.py        主循环 / Main loop
│   │   ├── tools.py        工具定义与执行 / Tool definitions
│   │   └── prompts.py      System prompt
│   └── web/                Web 应用 / Web application
│       ├── app.py          Flask 路由 / Flask routes
│       ├── templates/      HTML 模板 / HTML templates
│       └── static/         CSS & JS
├── scripts/ingest.py       数据导入脚本 / Data ingestion script
├── tests/                  测试 / Tests
├── architecture/           项目文档 / Project docs
└── config.py               全局配置 / Global config
```

---

## 许可证 | License

MIT
