# 开发进度

## v1.0 已完成（原型）

- [x] 项目骨架（目录结构、空文件）
- [x] architecture/ 文档初始化
- [x] config.py
- [x] requirements.txt
- [x] .env.example / .gitignore
- [x] src/ingestion/loader.py（HTML: BeautifulSoup，PDF: pdfplumber）
- [x] src/ingestion/chunker.py（段落优先，400 字/块，50 字重叠）
- [x] src/ingestion/pipeline.py（load → chunk → embed → store 串联）
- [x] src/retrieval/embedder.py（BAAI/bge-m3，支持批量）
- [x] src/retrieval/store.py（ChromaDB，cosine 相似度，支持增量写入）
- [x] scripts/ingest.py（一次性摄入入口）
- [x] src/agent/prompts.py（中文 system prompt，含检索原则和回答规范）
- [x] src/agent/tools.py（TOOL_SCHEMAS + execute_search_policy / execute_get_policy_detail）
- [x] src/agent/agent.py（PolicyAgent，tool_use 多轮循环，依赖注入，MAX_TOOL_ROUNDS=5）
- [x] src/web/app.py（Flask，GET /，POST /api/chat，Agent 单例懒加载）
- [x] src/web/templates/index.html（聊天 UI，欢迎页，示例问题按钮）
- [x] src/web/static/css/style.css（气泡样式，来源标签，加载动画）
- [x] src/web/static/js/chat.js（历史管理，Enter 发送，自动滚动）

### v1.0 测试
- [x] tests/test_loader.py（9 个用例）
- [x] tests/test_retrieval.py（14 个用例）
- [x] tests/test_agent.py（28 个单元 + 3 个集成）
- [x] tests/test_web.py（12 个单元 + 1 个集成）
- 单元测试合计 63/63 通过

---

## v2.0 升级计划

详见 [upgrade_plan.md](upgrade_plan.md)

### Phase 1：评估基础 + 文档处理升级
- [x] 1.1 评估数据集构建（50条问答对，覆盖8种类型16篇文档）
- [x] 1.2 RAGAS 接入 + 评估工具（retrieval_eval + answer_eval + run_eval.py）
- [x] 1.3 文档解析器升级（PDF/HTML/MD → 标准化 Markdown，25个测试）
- [x] 1.4 元数据增强（正则 + Haiku 兜底，32个测试）
- [x] 1.5 表格处理（自然语言 + Q&K 生成，16个测试）
- [x] 1.6 Cleaner + Pipeline v2（标准化输出，20个测试）
- [x] 1.7 架构文档更新

### Phase 2：分块 + 检索升级
- [x] 2.1 语义分块（Markdown 标题层级 + 父子 chunk，26个测试）
- [x] 2.2 BM25 索引（jieba + 自定义政策词典，16个测试）
- [x] 2.3 混合检索（向量+BM25+RRF+元数据过滤，12个测试）
- [x] 2.4 Reranker（BGE-Reranker-v2-m3，6个测试）
- [ ] 2.5 评估验证（对比 Phase 1 基准线）

### Phase 3：对话体验升级
- [ ] 3.1 流式输出（Flask SSE + 前端 EventSource）
- [ ] 3.2 多轮对话（滑动窗口 10轮 + Query 改写）
- [ ] 3.3 语义缓存（LRU+TTL+source失效）
- [ ] 3.4 Agent 策略优化（Tool 扩展 + Prompt 优化）
- [ ] 3.5 评估验证

### Phase 4：评估体系完善 + 整体调优
- [ ] 4.1 RAGAS 完整指标 + LLM-as-Judge 补充
- [ ] 4.2 数据驱动调优（chunk大小、RRF k值、Reranker阈值）
- [ ] 4.3 评估数据集扩充（100+条）
