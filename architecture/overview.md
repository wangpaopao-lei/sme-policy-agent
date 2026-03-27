# 项目概览

## 项目目标
面向国家中小企业政策信息平台的问答 Agent 演示原型。用户可通过 Web 界面提问，Agent 自主决定检索策略，从政策文档库中找到相关信息并作答。

## 技术栈
| 组件 | 选型 | 说明 |
|------|------|------|
| LLM | Claude API (claude-sonnet-4-6) | 通过 Anthropic SDK 调用 |
| Embedding | BAAI/bge-m3 | 本地模型，支持中文 |
| 向量数据库 | ChromaDB | 本地持久化 |
| Web 框架 | Flask + 原生 JS | 简洁前端，聊天气泡 UI |
| PDF 解析 | pdfplumber | |
| HTML 解析 | BeautifulSoup4 | |

## 数据来源
手工下载的政策文件，位于 `data/` 目录，包含 HTML 和 PDF 两种格式。

## Agent 能力
方案 B：Claude 自主决定是否检索、检索几次，通过 tool_use 多轮循环实现。
工具清单：
- `search_policy(query, top_k)` — 语义检索相关政策片段
- `get_policy_detail(source)` — 获取某篇政策的完整摘要

## 关键约束
- 数据为静态导入，不需要实时爬取
- 演示用途，优先清晰可读，不过度优化性能
