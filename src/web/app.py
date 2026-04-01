import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from flask import Flask, request, jsonify, render_template, Response
from src.agent.agent import PolicyAgent
from src.conversation.history import ConversationHistory
from src.conversation.query_rewriter import QueryRewriter

app = Flask(__name__)

# 单例：Agent 初始化较重（加载 embedding 模型），只初始化一次
_agent = None

# 会话管理：session_id → ConversationHistory
# 生产环境应用 Redis，这里简化用内存 dict
_sessions: dict[str, ConversationHistory] = {}


def get_agent() -> PolicyAgent:
    global _agent
    if _agent is None:
        # 默认 v1 模式（兼容），v2 模式需要传入 searcher 等组件
        _agent = PolicyAgent()
    return _agent


def get_session(session_id: str) -> ConversationHistory:
    if session_id not in _sessions:
        _sessions[session_id] = ConversationHistory(max_rounds=10)
    return _sessions[session_id]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    """非流式接口（保留向后兼容）"""
    data = request.get_json(silent=True)
    if not data or not data.get("message", "").strip():
        return jsonify({"error": "message 不能为空"}), 400

    user_message = data["message"].strip()
    history = data.get("history", [])

    try:
        result = get_agent().chat(user_message, history=history)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    """SSE 流式接口"""
    data = request.get_json(silent=True)
    if not data or not data.get("message", "").strip():
        return jsonify({"error": "message 不能为空"}), 400

    user_message = data["message"].strip()
    history = data.get("history", [])

    def generate():
        try:
            for event in get_agent().chat_stream(user_message, history=history):
                if event["type"] == "text":
                    yield f"data: {json.dumps({'type': 'text', 'text': event['text']}, ensure_ascii=False)}\n\n"
                elif event["type"] == "done":
                    yield f"data: {json.dumps({'type': 'done', 'sources': event['sources']}, ensure_ascii=False)}\n\n"
                elif event["type"] == "error":
                    yield f"data: {json.dumps({'type': 'error', 'message': event['message']}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/session/clear", methods=["POST"])
def clear_session():
    """清空会话历史"""
    data = request.get_json(silent=True)
    session_id = (data or {}).get("session_id", "default")
    if session_id in _sessions:
        _sessions[session_id].clear()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, port=18336)
