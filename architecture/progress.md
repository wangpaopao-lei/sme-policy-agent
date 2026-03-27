# 开发进度

## 已完成
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

## 已完成（续）
- [x] src/agent/prompts.py（中文 system prompt，含检索原则和回答规范）
- [x] src/agent/tools.py（TOOL_SCHEMAS + execute_search_policy / execute_get_policy_detail）
- [x] src/agent/agent.py（PolicyAgent，tool_use 多轮循环，依赖注入，MAX_TOOL_ROUNDS=5）
- [x] pytest.ini（注册 integration mark）

## 已完成（续）
- [x] src/web/app.py（Flask，GET /，POST /api/chat，Agent 单例懒加载）
- [x] src/web/templates/index.html（聊天 UI，欢迎页，示例问题按钮）
- [x] src/web/static/css/style.css（气泡样式，来源标签，加载动画）
- [x] src/web/static/js/chat.js（历史管理，Enter 发送，自动滚动）

## 待开发
- 无（所有功能已完成）

## 测试
- [x] tests/test_loader.py（9 个用例：HTML解析、标题回退、脚本清理、load_all、真实数据集成）
- [x] tests/test_retrieval.py（14 个用例：分块逻辑、chunk_id、ChromaDB 增删查）
- [x] tests/test_agent.py（28 个单元用例 + 3 个集成用例）
  - 工具执行、schema 格式、来源提取、去重
  - Agent 多轮 tool_use 循环、历史传递、超限兜底
- [x] tests/test_web.py（12 个单元用例 + 1 个集成用例）
  - 路由、参数校验、错误处理、message strip、history 传递
  - 集成用例标记 @pytest.mark.integration，需真实环境运行
- 单元测试合计 63/63 通过
