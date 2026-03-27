import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import config
from src.agent.prompts import SYSTEM_PROMPT
from src.agent.tools import TOOL_SCHEMAS, execute_tool

MAX_TOOL_ROUNDS = 5  # 防止无限循环


class PolicyAgent:
    def __init__(self, client=None, embedder=None, store=None):
        """
        支持依赖注入，方便测试时传入 mock 对象。
        不传参数时自动初始化真实依赖（懒加载，避免测试时的无关 import 开销）。
        """
        if client is not None:
            self.client = client
        else:
            import anthropic
            import config
            self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

        if embedder is not None:
            self.embedder = embedder
        else:
            import config
            from src.retrieval.embedder import Embedder
            self.embedder = Embedder(model_name=config.EMBEDDING_MODEL)

        if store is not None:
            self.store = store
        else:
            import config
            from src.retrieval.store import PolicyStore
            self.store = PolicyStore(
                chroma_path=config.CHROMA_PATH,
                collection_name=config.CHROMA_COLLECTION,
            )

    def chat(self, user_message: str, history: list[dict] = None) -> dict:
        """
        处理一轮对话，支持多轮 tool_use 循环。

        参数：
            user_message: 用户当前输入
            history: 历史消息列表，格式为 [{"role": "user"|"assistant", "content": str}, ...]

        返回：
            {
                "answer": str,         # Claude 的最终回复
                "sources": list[str]   # 本轮引用的来源文件名（去重）
            }
        """
        messages = self._build_messages(history or [], user_message)
        sources: list[str] = []

        for _ in range(MAX_TOOL_ROUNDS):
            response = self.client.messages.create(
                model=config.CLAUDE_MODEL,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=TOOL_SCHEMAS,
                max_tokens=4096,
            )

            if response.stop_reason == "end_turn":
                answer = self._extract_text(response)
                return {"answer": answer, "sources": _dedup(sources)}

            if response.stop_reason == "tool_use":
                # 把 assistant 的回复（含 tool_use block）加入消息历史
                messages.append({"role": "assistant", "content": response.content})

                # 执行所有工具，收集结果
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = execute_tool(
                            name=block.name,
                            tool_input=block.input,
                            embedder=self.embedder,
                            store=self.store,
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                        # 收集 search_policy 调用的来源
                        if block.name == "search_policy":
                            sources.extend(_extract_sources(result))

                messages.append({"role": "user", "content": tool_results})
                continue

            # 其他 stop_reason（max_tokens 等）
            answer = self._extract_text(response)
            return {"answer": answer, "sources": _dedup(sources)}

        # 超出最大工具轮次，返回当前已有内容
        return {
            "answer": "抱歉，处理您的问题时遇到了异常，请重试。",
            "sources": _dedup(sources),
        }

    # ── 私有辅助方法 ───────────────────────────────────────────────────────────

    def _build_messages(self, history: list[dict], user_message: str) -> list[dict]:
        """将历史记录和当前问题组合成 messages 列表"""
        messages = []
        for turn in history:
            messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": user_message})
        return messages

    def _extract_text(self, response) -> str:
        """从 response.content 中提取纯文本（只取 type=='text' 的 block）"""
        parts = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                parts.append(block.text)
        return "\n".join(parts).strip()


# ── 模块级工具函数 ─────────────────────────────────────────────────────────────

def _dedup(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _extract_sources(search_result: str) -> list[str]:
    """从 search_policy 返回的文本中提取来源文件名"""
    sources = []
    for line in search_result.splitlines():
        if line.startswith("来源文件："):
            source = line.removeprefix("来源文件：").strip()
            if source:
                sources.append(source)
    return sources
