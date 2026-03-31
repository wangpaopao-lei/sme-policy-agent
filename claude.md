企业政策问答 Agent
## 项目概述
面向中小企业政策信息平台的 RAG 问答系统。用户通过 Web 界面提问，Agent 自主检索政策文档库并生成回答。

- 文档处理：支持 PDF/HTML/Markdown，pdfplumber 解析 + markdownify 转换，LLM(Haiku) 兜底，输出标准化 Markdown
- 分块：Markdown 标题层级语义分块 + 父子 chunk（子 chunk 检索，父 chunk 送 Claude）
- Embedding：BGE-M3（本地）
- 存储：ChromaDB（向量）+ rank_bm25 + jieba（关键词）
- 检索：混合检索（向量+BM25）→ RRF 融合 → BGE-Reranker 精排 → 元数据过滤
- Agent：Anthropic SDK，Claude Sonnet，Tool use 多轮循环
- 对话：滑动窗口 10 轮 + Query 改写 + 语义缓存
- Web：Flask + SSE 流式输出
- 评估：RAGAS + 自建 LLM-as-Judge

当前处于 v2.0 升级阶段，分 4 个 Phase 实施，详见 architecture/upgrade_plan.md

## 规则
- 每次回答我需要用”王先生”开头
- 写代码前先告诉我方案，批准了再动手
- 需求模糊的情况先提问
- 每次写完代码后更新 architecture 目录
- 新增代码后需要添加单元测试或集成测试，视修改的类别而定

## Git 工作流
- 每个 Phase 开独立分支：`phase1/doc-parsing`、`phase2/retrieval`、`phase3/conversation`、`phase4/evaluation`
- main 始终保持可运行状态
- Phase 完成后创建 PR 合并回 main，再开下一个 Phase 的分支
- Commit 粒度：一个功能模块 + 对应测试 = 一个 commit，不要攒太多也不要太碎
- 代码和对应的测试必须在同一个 commit 中
- Commit Message 使用 Conventional Commits：feat / fix / refactor / test / docs / chore