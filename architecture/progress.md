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
- [x] 3.1 多轮对话（滑动窗口 10轮 + Claude Query 改写，15个测试）
- [x] 3.2 语义缓存（LRU+TTL+source失效，SQLite持久化，9个测试）
- [x] 3.3 流式输出（Flask SSE + agent.chat_stream + 前端 EventSource，4个测试）
- [x] 3.4 Agent 策略优化（Tool filters 参数 + Prompt few-shot + 置信度引导）

### Phase 4：模块整合 + 评估调优
- [x] 4.1 v2 摄入脚本（pipeline_v2 → 父子分块 → 双索引入库，4个测试）
- [x] 4.2 模块整合（hybrid search + conversation 接入 agent/web，44个现有测试通过）
- [x] 4.3 评估数据集扩充（50→105条，覆盖8类 x 16篇文档）
- [x] 4.4 参数调优框架（CLI sweep 实验 + 对比报告，5个测试）
- [x] 4.5 参数调优实验完成，最优配置：top_k=7, rrf_k=60, rerank=off
- [x] 4.6 run_eval.py 升级接入 v2 混合检索 + 扩展名归一化

---

## v2.0 最终评估结果

| 指标 | v1 基准线 (50条) | v2 最终 (105条) |
|------|-----------------|----------------|
| Recall@7 | — | **0.97** |
| MRR | 0.922 | **0.932** |
| 失败数 | 1 | 3 |

最优参数配置：top_k=7, rrf_k=60, rerank=off
