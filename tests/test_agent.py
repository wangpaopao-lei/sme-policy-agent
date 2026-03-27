"""
Agent 层测试

单元测试（无需真实 API）：直接运行
    pytest tests/test_agent.py -v

集成测试（需要真实 Claude API Key + 已初始化的 ChromaDB）：
    pytest tests/test_agent.py -v -m integration
    前提：已设置 ANTHROPIC_API_KEY 环境变量，且已运行 python scripts/ingest.py
"""
import sys
import os
from unittest.mock import MagicMock, patch, call
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.tools import (
    execute_search_policy,
    execute_get_policy_detail,
    execute_tool,
    TOOL_SCHEMAS,
)
from src.agent.agent import PolicyAgent, _dedup, _extract_sources


# ── 工具函数单元测试 ───────────────────────────────────────────────────────────

class TestExtractSources:
    def test_extracts_source_from_search_result(self):
        result = (
            "[片段 1]\n"
            "来源文件：policy_a.html\n"
            "文件标题：政策A\n"
            "相关度：0.95\n"
            "内容：政策内容\n"
            "---\n"
            "[片段 2]\n"
            "来源文件：policy_b.pdf\n"
            "文件标题：政策B\n"
            "相关度：0.90\n"
            "内容：更多内容\n"
        )
        sources = _extract_sources(result)
        assert "policy_a.html" in sources
        assert "policy_b.pdf" in sources

    def test_returns_empty_for_no_match(self):
        assert _extract_sources("未找到相关政策内容。") == []

    def test_returns_empty_for_empty_string(self):
        assert _extract_sources("") == []


class TestDedup:
    def test_removes_duplicates(self):
        assert _dedup(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]

    def test_preserves_order(self):
        assert _dedup(["c", "a", "b"]) == ["c", "a", "b"]

    def test_empty_list(self):
        assert _dedup([]) == []


# ── 工具执行单元测试 ───────────────────────────────────────────────────────────

class TestExecuteSearchPolicy:
    def _make_embedder(self):
        embedder = MagicMock()
        embedder.embed.return_value = [0.1] * 8
        return embedder

    def _make_store(self, chunks):
        store = MagicMock()
        store.query.return_value = chunks
        return store

    def test_returns_formatted_result(self):
        chunks = [
            {"text": "政策内容", "source": "a.html", "title": "政策A", "chunk_index": 0, "score": 0.95}
        ]
        result = execute_search_policy("中小企业", 5, self._make_embedder(), self._make_store(chunks))
        assert "来源文件：a.html" in result
        assert "政策内容" in result
        assert "0.95" in result

    def test_returns_message_when_no_results(self):
        result = execute_search_policy("xyz", 5, self._make_embedder(), self._make_store([]))
        assert "未找到" in result

    def test_top_k_capped_at_10(self):
        store = self._make_store([])
        execute_search_policy("query", 999, self._make_embedder(), store)
        _, kwargs = store.query.call_args
        assert kwargs["top_k"] <= 10

    def test_top_k_minimum_is_1(self):
        store = self._make_store([])
        execute_search_policy("query", 0, self._make_embedder(), store)
        _, kwargs = store.query.call_args
        assert kwargs["top_k"] >= 1

    def test_calls_embedder_with_query(self):
        embedder = self._make_embedder()
        execute_search_policy("贷款贴息", 3, embedder, self._make_store([]))
        embedder.embed.assert_called_once_with("贷款贴息")


class TestExecuteGetPolicyDetail:
    def test_returns_full_text(self):
        store = MagicMock()
        store.get_by_source.return_value = [
            {"text": "第一段", "source": "a.html", "title": "政策A", "chunk_index": 0},
            {"text": "第二段", "source": "a.html", "title": "政策A", "chunk_index": 1},
        ]
        result = execute_get_policy_detail("a.html", store)
        assert "第一段" in result
        assert "第二段" in result
        assert "a.html" in result

    def test_returns_message_when_not_found(self):
        store = MagicMock()
        store.get_by_source.return_value = []
        result = execute_get_policy_detail("missing.html", store)
        assert "未找到" in result


class TestExecuteTool:
    def test_routes_search_policy(self):
        embedder = MagicMock()
        embedder.embed.return_value = [0.1] * 8
        store = MagicMock()
        store.query.return_value = []
        result = execute_tool("search_policy", {"query": "政策"}, embedder, store)
        assert isinstance(result, str)

    def test_routes_get_policy_detail(self):
        store = MagicMock()
        store.get_by_source.return_value = []
        result = execute_tool("get_policy_detail", {"source": "a.html"}, MagicMock(), store)
        assert isinstance(result, str)

    def test_unknown_tool_returns_error_message(self):
        result = execute_tool("nonexistent_tool", {}, MagicMock(), MagicMock())
        assert "未知工具" in result


# ── Tool Schema 格式验证 ───────────────────────────────────────────────────────

class TestToolSchemas:
    def test_all_tools_have_required_fields(self):
        for tool in TOOL_SCHEMAS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool

    def test_search_policy_schema(self):
        schema = next(t for t in TOOL_SCHEMAS if t["name"] == "search_policy")
        props = schema["input_schema"]["properties"]
        assert "query" in props
        assert "top_k" in props
        assert schema["input_schema"]["required"] == ["query"]

    def test_get_policy_detail_schema(self):
        schema = next(t for t in TOOL_SCHEMAS if t["name"] == "get_policy_detail")
        props = schema["input_schema"]["properties"]
        assert "source" in props
        assert schema["input_schema"]["required"] == ["source"]


# ── PolicyAgent 单元测试（mock Claude 客户端）─────────────────────────────────

def _make_text_block(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_tool_use_block(tool_id: str, name: str, input_data: dict):
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = input_data
    return block


def _make_response(stop_reason: str, content: list):
    response = MagicMock()
    response.stop_reason = stop_reason
    response.content = content
    return response


class TestPolicyAgentUnit:
    @pytest.fixture
    def agent(self):
        """通过依赖注入创建 agent，无需 mock 外部模块"""
        mock_client = MagicMock()
        mock_embedder = MagicMock()
        mock_store = MagicMock()
        a = PolicyAgent(client=mock_client, embedder=mock_embedder, store=mock_store)
        return a

    def test_build_messages_with_no_history(self, agent):
        msgs = agent._build_messages([], "你好")
        assert len(msgs) == 1
        assert msgs[0] == {"role": "user", "content": "你好"}

    def test_build_messages_with_history(self, agent):
        history = [
            {"role": "user", "content": "第一问"},
            {"role": "assistant", "content": "第一答"},
        ]
        msgs = agent._build_messages(history, "第二问")
        assert len(msgs) == 3
        assert msgs[-1] == {"role": "user", "content": "第二问"}

    def test_extract_text_from_text_block(self, agent):
        response = _make_response("end_turn", [_make_text_block("这是回答")])
        assert agent._extract_text(response) == "这是回答"

    def test_extract_text_ignores_non_text_blocks(self, agent):
        tool_block = _make_tool_use_block("id1", "search_policy", {"query": "test"})
        text_block = _make_text_block("最终回答")
        response = _make_response("end_turn", [tool_block, text_block])
        assert agent._extract_text(response) == "最终回答"

    def test_chat_direct_answer_no_tool_use(self, agent):
        """Claude 直接回答，不调用工具"""
        response = _make_response("end_turn", [_make_text_block("直接回答内容")])
        agent.client.messages.create.return_value = response

        result = agent.chat("你好")
        assert result["answer"] == "直接回答内容"
        assert result["sources"] == []
        assert agent.client.messages.create.call_count == 1

    def test_chat_one_tool_use_round(self, agent):
        """Claude 调用一次工具，然后给出最终回答"""
        agent.store.query.return_value = [
            {"text": "政策片段", "source": "a.html", "title": "政策A",
             "chunk_index": 0, "score": 0.9}
        ]
        agent.embedder.embed.return_value = [0.1] * 8

        tool_response = _make_response("tool_use", [
            _make_tool_use_block("tool_1", "search_policy", {"query": "贷款", "top_k": 5})
        ])
        final_response = _make_response("end_turn", [_make_text_block("根据政策，贷款支持...")])
        agent.client.messages.create.side_effect = [tool_response, final_response]

        result = agent.chat("贷款政策有哪些？")
        assert "贷款支持" in result["answer"]
        assert "a.html" in result["sources"]
        assert agent.client.messages.create.call_count == 2

    def test_chat_collects_sources_from_multiple_searches(self, agent):
        """多次检索时，来源应全部收集且去重"""
        agent.embedder.embed.return_value = [0.1] * 8
        agent.store.query.side_effect = [
            [{"text": "内容A", "source": "a.html", "title": "A", "chunk_index": 0, "score": 0.9}],
            [{"text": "内容B", "source": "b.html", "title": "B", "chunk_index": 0, "score": 0.8},
             {"text": "内容C", "source": "a.html", "title": "A", "chunk_index": 1, "score": 0.7}],
        ]

        round1 = _make_response("tool_use", [
            _make_tool_use_block("t1", "search_policy", {"query": "担保"})
        ])
        round2 = _make_response("tool_use", [
            _make_tool_use_block("t2", "search_policy", {"query": "贴息"})
        ])
        final = _make_response("end_turn", [_make_text_block("综合以上政策...")])
        agent.client.messages.create.side_effect = [round1, round2, final]

        result = agent.chat("担保和贴息政策")
        assert set(result["sources"]) == {"a.html", "b.html"}
        assert len(result["sources"]) == 2  # a.html 只出现一次（去重）

    def test_chat_exceeds_max_rounds_returns_fallback(self, agent):
        """超出最大工具轮次时返回兜底消息"""
        agent.embedder.embed.return_value = [0.1] * 8
        agent.store.query.return_value = []

        # 每次都返回 tool_use，触发最大轮次限制
        tool_response = _make_response("tool_use", [
            _make_tool_use_block("t1", "search_policy", {"query": "test"})
        ])
        agent.client.messages.create.return_value = tool_response

        result = agent.chat("无限循环问题")
        assert "抱歉" in result["answer"]

    def test_chat_passes_history_to_messages(self, agent):
        """历史消息应正确传入 Claude"""
        response = _make_response("end_turn", [_make_text_block("回答")])
        agent.client.messages.create.return_value = response

        history = [
            {"role": "user", "content": "上一个问题"},
            {"role": "assistant", "content": "上一个回答"},
        ]
        agent.chat("当前问题", history=history)

        call_kwargs = agent.client.messages.create.call_args[1]
        messages = call_kwargs["messages"]
        assert messages[0]["content"] == "上一个问题"
        assert messages[1]["content"] == "上一个回答"
        assert messages[2]["content"] == "当前问题"


# ── 集成测试（需要真实环境）───────────────────────────────────────────────────

@pytest.mark.integration
class TestPolicyAgentIntegration:
    """
    集成测试前提：
    1. 已设置环境变量 ANTHROPIC_API_KEY
    2. 已运行 python scripts/ingest.py 完成数据导入

    运行命令：
        pytest tests/test_agent.py -v -m integration
    """

    @pytest.fixture(scope="class")
    def agent(self):
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            pytest.skip("未设置 ANTHROPIC_API_KEY，跳过集成测试")
        return PolicyAgent()

    def test_chat_returns_valid_structure(self, agent):
        result = agent.chat("中小企业有哪些贷款支持政策？")
        assert isinstance(result, dict)
        assert "answer" in result
        assert "sources" in result
        assert isinstance(result["answer"], str)
        assert len(result["answer"]) > 0
        assert isinstance(result["sources"], list)

    def test_chat_with_history(self, agent):
        history = [
            {"role": "user", "content": "什么是设备更新贷款贴息政策？"},
            {"role": "assistant", "content": "设备更新贷款贴息政策是...（模拟历史回答）"},
        ]
        result = agent.chat("这个政策的申请条件是什么？", history=history)
        assert len(result["answer"]) > 0

    def test_chat_irrelevant_question(self, agent):
        """非政策问题应礼貌拒绝，不应检索"""
        result = agent.chat("今天天气怎么样？")
        assert len(result["answer"]) > 0
