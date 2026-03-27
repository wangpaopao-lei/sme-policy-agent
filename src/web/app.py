import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from flask import Flask, request, jsonify, render_template
from src.agent.agent import PolicyAgent

app = Flask(__name__)

# 单例：Agent 初始化较重（加载 embedding 模型），只初始化一次
_agent = None


def get_agent() -> PolicyAgent:
    global _agent
    if _agent is None:
        _agent = PolicyAgent()
    return _agent


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, port=18336)
