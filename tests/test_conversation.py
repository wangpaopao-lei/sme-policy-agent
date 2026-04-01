"""对话管理测试"""

from unittest.mock import MagicMock

import pytest

from src.conversation.history import ConversationHistory
from src.conversation.query_rewriter import QueryRewriter


# ============================================================
# 对话历史测试
# ============================================================


class TestConversationHistory:
    def test_add_messages(self):
        history = ConversationHistory(max_rounds=10)
        history.add_user("你好")
        history.add_assistant("你好！有什么可以帮助您？")

        messages = history.get_messages()
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

    def test_sliding_window(self):
        history = ConversationHistory(max_rounds=2)

        # 添加 3 轮对话
        for i in range(3):
            history.add_user(f"问题{i}")
            history.add_assistant(f"回答{i}")

        messages = history.get_messages()
        # 只保留最近 2 轮 = 4 条消息
        assert len(messages) == 4
        assert messages[0]["content"] == "问题1"
        assert messages[-1]["content"] == "回答2"

    def test_trim_ensures_user_first(self):
        """裁剪后第一条消息应该是 user"""
        history = ConversationHistory(max_rounds=1)

        history.add_user("问题0")
        history.add_assistant("回答0")
        history.add_user("问题1")
        history.add_assistant("回答1")

        messages = history.get_messages()
        assert messages[0]["role"] == "user"

    def test_get_recent_context(self):
        history = ConversationHistory()
        history.add_user("贷款贴息政策是什么？")
        history.add_assistant("中央财政给予年化1.5个百分点的贴息。")

        context = history.get_recent_context(n_rounds=1)
        assert "用户: 贷款贴息政策是什么？" in context
        assert "助手: 中央财政" in context

    def test_get_recent_context_truncates_long_messages(self):
        history = ConversationHistory()
        history.add_user("短问题")
        history.add_assistant("很长的回答" * 100)

        context = history.get_recent_context()
        assert "..." in context

    def test_clear(self):
        history = ConversationHistory()
        history.add_user("问题")
        history.add_assistant("回答")
        history.clear()

        assert len(history) == 0
        assert history.get_messages() == []

    def test_len(self):
        history = ConversationHistory()
        assert len(history) == 0
        history.add_user("问题")
        assert len(history) == 1

    def test_empty_context(self):
        history = ConversationHistory()
        context = history.get_recent_context()
        assert context == ""

    def test_returns_copy(self):
        """get_messages 应返回副本，修改不影响原始数据"""
        history = ConversationHistory()
        history.add_user("问题")

        messages = history.get_messages()
        messages.clear()

        assert len(history) == 1


# ============================================================
# Query 改写器测试
# ============================================================


class TestQueryRewriter:
    def _make_rewriter(self, response_text: str = "改写后的查询"):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=response_text)]
        mock_client.messages.create.return_value = mock_response
        return QueryRewriter(client=mock_client), mock_client

    def test_rewrite_with_pronoun(self):
        rewriter, mock_client = self._make_rewriter("中小微企业贷款贴息比例是多少")

        result = rewriter.rewrite(
            query="它的贴息比例是多少",
            history_context="用户: 中小微企业贷款贴息政策是什么？\n助手: 中央财政给予年化1.5个百分点的贴息。",
        )

        assert result == "中小微企业贷款贴息比例是多少"
        mock_client.messages.create.assert_called_once()

    def test_no_rewrite_without_history(self):
        rewriter, mock_client = self._make_rewriter()

        result = rewriter.rewrite("贷款贴息政策是什么", history_context="")

        assert result == "贷款贴息政策是什么"
        mock_client.messages.create.assert_not_called()

    def test_no_rewrite_for_complete_query(self):
        """完整的长查询不包含指代词时不改写"""
        rewriter, mock_client = self._make_rewriter()

        result = rewriter.rewrite(
            query="中小微企业贷款贴息政策支持哪些产业领域",
            history_context="用户: 你好\n助手: 你好！",
        )

        assert result == "中小微企业贷款贴息政策支持哪些产业领域"
        mock_client.messages.create.assert_not_called()

    def test_short_query_triggers_rewrite(self):
        """短问题触发改写"""
        rewriter, mock_client = self._make_rewriter("中小微企业贷款贴息政策的经办银行有哪些")

        result = rewriter.rewrite(
            query="经办银行呢",
            history_context="用户: 贷款贴息政策\n助手: ...",
        )

        mock_client.messages.create.assert_called_once()

    def test_llm_failure_returns_original(self):
        """LLM 调用失败时返回原 query"""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API error")
        rewriter = QueryRewriter(client=mock_client)

        result = rewriter.rewrite(
            query="它的比例是多少",
            history_context="用户: 贷款\n助手: 回答",
        )

        assert result == "它的比例是多少"

    def test_abnormal_response_returns_original(self):
        """LLM 返回异常结果时返回原 query"""
        rewriter, _ = self._make_rewriter("x")  # 太短

        result = rewriter.rewrite(
            query="它的贴息比例是多少",
            history_context="用户: 贷款\n助手: 回答",
        )

        assert result == "它的贴息比例是多少"
