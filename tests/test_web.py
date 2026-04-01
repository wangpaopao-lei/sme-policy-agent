"""
Flask web 层测试

单元测试（mock Agent，无需真实 API）：
    pytest tests/test_web.py -v

集成测试（需要真实 Claude API + 已导入数据）：
    pytest tests/test_web.py -v -m integration
"""
import sys
import os
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def client():
    """每个测试使用独立的 Flask 测试客户端，并 mock 掉 PolicyAgent"""
    mock_agent = MagicMock()
    with patch("src.web.app._agent", mock_agent):
        from src.web.app import app
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c, mock_agent


# ── GET / ─────────────────────────────────────────────────────────────────────

class TestIndexRoute:
    def test_returns_200(self, client):
        c, _ = client
        res = c.get("/")
        assert res.status_code == 200

    def test_returns_html(self, client):
        c, _ = client
        res = c.get("/")
        assert b"text/html" in res.content_type.encode() or res.status_code == 200
        assert "中小企业" in res.data.decode("utf-8")


# ── POST /api/chat ─────────────────────────────────────────────────────────────

class TestChatRoute:
    def test_valid_request_returns_answer(self, client):
        c, mock_agent = client
        mock_agent.chat.return_value = {
            "answer": "根据政策文件，贷款贴息政策...",
            "sources": ["a.html"],
        }
        res = c.post("/api/chat", json={"message": "贷款政策"})
        assert res.status_code == 200
        data = res.get_json()
        assert data["answer"] == "根据政策文件，贷款贴息政策..."
        assert data["sources"] == ["a.html"]

    def test_passes_message_and_history_to_agent(self, client):
        c, mock_agent = client
        mock_agent.chat.return_value = {"answer": "回答", "sources": []}
        history = [
            {"role": "user", "content": "上一问"},
            {"role": "assistant", "content": "上一答"},
        ]
        c.post("/api/chat", json={"message": "当前问", "history": history})
        mock_agent.chat.assert_called_once_with("当前问", history=history)

    def test_empty_message_returns_400(self, client):
        c, _ = client
        res = c.post("/api/chat", json={"message": ""})
        assert res.status_code == 400

    def test_whitespace_message_returns_400(self, client):
        c, _ = client
        res = c.post("/api/chat", json={"message": "   "})
        assert res.status_code == 400

    def test_missing_message_field_returns_400(self, client):
        c, _ = client
        res = c.post("/api/chat", json={})
        assert res.status_code == 400

    def test_non_json_body_returns_400(self, client):
        c, _ = client
        res = c.post("/api/chat", data="not json", content_type="text/plain")
        assert res.status_code == 400

    def test_missing_history_defaults_to_empty(self, client):
        c, mock_agent = client
        mock_agent.chat.return_value = {"answer": "回答", "sources": []}
        c.post("/api/chat", json={"message": "问题"})
        mock_agent.chat.assert_called_once_with("问题", history=[])

    def test_agent_exception_returns_500(self, client):
        c, mock_agent = client
        mock_agent.chat.side_effect = RuntimeError("模型加载失败")
        res = c.post("/api/chat", json={"message": "问题"})
        assert res.status_code == 500
        assert "error" in res.get_json()

    def test_response_contains_sources_list(self, client):
        c, mock_agent = client
        mock_agent.chat.return_value = {"answer": "回答", "sources": ["a.html", "b.pdf"]}
        res = c.post("/api/chat", json={"message": "问题"})
        data = res.get_json()
        assert isinstance(data["sources"], list)
        assert len(data["sources"]) == 2

    def test_message_is_stripped(self, client):
        """前后空格应被去除后传给 agent"""
        c, mock_agent = client
        mock_agent.chat.return_value = {"answer": "回答", "sources": []}
        c.post("/api/chat", json={"message": "  贷款政策  "})
        mock_agent.chat.assert_called_once_with("贷款政策", history=[])


# ── POST /api/chat/stream（SSE）─────────────────────────────────────────────────

class TestStreamRoute:
    def test_stream_returns_sse(self, client):
        c, mock_agent = client
        mock_agent.chat_stream.return_value = iter([
            {"type": "text", "text": "你好"},
            {"type": "text", "text": "，世界"},
            {"type": "done", "sources": ["a.txt"]},
        ])

        res = c.post("/api/chat/stream", json={"message": "你好"})
        assert res.status_code == 200
        assert "text/event-stream" in res.content_type

        # 解析 SSE 数据
        data = res.data.decode("utf-8")
        events = [line.removeprefix("data: ") for line in data.strip().split("\n\n") if line.startswith("data: ")]

        import json
        parsed = [json.loads(e) for e in events]
        assert parsed[0] == {"type": "text", "text": "你好"}
        assert parsed[1] == {"type": "text", "text": "，世界"}
        assert parsed[2]["type"] == "done"
        assert parsed[2]["sources"] == ["a.txt"]

    def test_stream_empty_message_returns_400(self, client):
        c, _ = client
        res = c.post("/api/chat/stream", json={"message": ""})
        assert res.status_code == 400

    def test_stream_error_event(self, client):
        c, mock_agent = client
        mock_agent.chat_stream.return_value = iter([
            {"type": "error", "message": "测试错误"},
        ])

        res = c.post("/api/chat/stream", json={"message": "问题"})
        data = res.data.decode("utf-8")
        assert "error" in data
        assert "测试错误" in data

    def test_stream_exception_returns_error_event(self, client):
        c, mock_agent = client
        mock_agent.chat_stream.side_effect = RuntimeError("爆了")

        res = c.post("/api/chat/stream", json={"message": "问题"})
        data = res.data.decode("utf-8")
        assert "error" in data


# ── 集成测试 ───────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestWebIntegration:
    """
    集成测试前提：
    1. 已设置 ANTHROPIC_API_KEY 环境变量
    2. 已运行 python scripts/ingest.py

    运行命令：
        pytest tests/test_web.py -v -m integration
    """

    @pytest.fixture(scope="class")
    def real_client(self):
        from src.web.app import app, _agent
        # 重置单例，让 app 使用真实 Agent
        import src.web.app as web_app
        web_app._agent = None
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def test_full_chat_round_trip(self, real_client):
        res = real_client.post("/api/chat", json={
            "message": "中小企业贷款贴息政策有哪些？"
        })
        assert res.status_code == 200
        data = res.get_json()
        assert len(data["answer"]) > 0
        assert isinstance(data["sources"], list)
