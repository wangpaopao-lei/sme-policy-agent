import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import config
from src.agent.prompts import SYSTEM_PROMPT
from src.agent.tools import TOOL_SCHEMAS, execute_tool

MAX_TOOL_ROUNDS = 5  # 防止无限循环


class PolicyAgent:
    def __init__(
        self,
        client=None,
        embedder=None,
        store=None,
        searcher=None,
        history_manager=None,
        query_rewriter=None,
        cache=None,
    ):
        """
        支持依赖注入，方便测试时传入 mock 对象。

        v2 模式：传入 searcher（HybridSearcher）+ conversation 组件
        v1 模式：传入 store（PolicyStore），保持向后兼容
        """
        if client is not None:
            self.client = client
        else:
            import anthropic
            self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

        if embedder is not None:
            self.embedder = embedder
        else:
            from src.retrieval.embedder import Embedder
            self.embedder = Embedder(model_name=config.EMBEDDING_MODEL)

        # v2: HybridSearcher（优先）
        self.searcher = searcher

        # v1 兼容：PolicyStore
        if store is not None:
            self.store = store
        elif searcher is None:
            from src.retrieval.store import PolicyStore
            self.store = PolicyStore(
                chroma_path=config.CHROMA_PATH,
                collection_name=config.CHROMA_COLLECTION,
            )
        else:
            self.store = None

        # conversation 组件（可选）
        self.history_manager = history_manager
        self.query_rewriter = query_rewriter
        self.cache = cache

    def chat(self, user_message: str, history: list[dict] = None) -> dict:
        """
        处理一轮对话，支持多轮 tool_use 循环。

        v2 增强：
        - 语义缓存命中时直接返回
        - query 改写（多轮对话指代消解）
        - 对话历史自动管理
        """
        # 1. 语义缓存检查
        if self.cache is not None:
            cached = self.cache.get(user_message)
            if cached is not None:
                answer, sources = cached
                if self.history_manager is not None:
                    self.history_manager.add_user(user_message)
                    self.history_manager.add_assistant(answer)
                return {"answer": answer, "sources": sources, "cached": True}

        # 2. Query 改写
        search_query = user_message
        if self.query_rewriter is not None and self.history_manager is not None:
            context = self.history_manager.get_recent_context(n_rounds=3)
            search_query = self.query_rewriter.rewrite(user_message, context)

        # 3. 对话历史
        if self.history_manager is not None:
            self.history_manager.add_user(user_message)
            messages = self._build_messages(
                self.history_manager.get_messages()[:-1],  # 不含刚加的 user
                user_message,
            )
        else:
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
                deduped_sources = _dedup(sources)

                # 写入缓存和历史
                if self.cache is not None:
                    self.cache.set(user_message, answer, deduped_sources)
                if self.history_manager is not None:
                    self.history_manager.add_assistant(answer)

                return {"answer": answer, "sources": deduped_sources}

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = execute_tool(
                            name=block.name,
                            tool_input=block.input,
                            embedder=self.embedder,
                            store=self.store,
                            searcher=self.searcher,
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                        if block.name == "search_policy":
                            sources.extend(_extract_sources(result))

                messages.append({"role": "user", "content": tool_results})
                continue

            answer = self._extract_text(response)
            deduped_sources = _dedup(sources)
            if self.history_manager is not None:
                self.history_manager.add_assistant(answer)
            return {"answer": answer, "sources": deduped_sources}

        return {
            "answer": "抱歉，处理您的问题时遇到了异常，请重试。",
            "sources": _dedup(sources),
        }

    def chat_stream(self, user_message: str, history: list[dict] = None):
        """
        流式版本的 chat。tool_use 阶段静默执行，最后一轮流式输出文本。
        """
        # 缓存命中时直接返回（不走流式）
        if self.cache is not None:
            cached = self.cache.get(user_message)
            if cached is not None:
                answer, sources = cached
                if self.history_manager is not None:
                    self.history_manager.add_user(user_message)
                    self.history_manager.add_assistant(answer)
                yield {"type": "text", "text": answer}
                yield {"type": "done", "sources": sources}
                return

        # Query 改写
        if self.query_rewriter is not None and self.history_manager is not None:
            context = self.history_manager.get_recent_context(n_rounds=3)
            self.query_rewriter.rewrite(user_message, context)

        # 对话历史
        if self.history_manager is not None:
            self.history_manager.add_user(user_message)
            messages = self._build_messages(
                self.history_manager.get_messages()[:-1],
                user_message,
            )
        else:
            messages = self._build_messages(history or [], user_message)

        sources: list[str] = []
        full_text = ""

        for round_idx in range(MAX_TOOL_ROUNDS):
            response = self.client.messages.create(
                model=config.CLAUDE_MODEL,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=TOOL_SCHEMAS,
                max_tokens=4096,
            )

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = execute_tool(
                            name=block.name,
                            tool_input=block.input,
                            embedder=self.embedder,
                            store=self.store,
                            searcher=self.searcher,
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                        if block.name == "search_policy":
                            sources.extend(_extract_sources(result))

                messages.append({"role": "user", "content": tool_results})
                continue

            try:
                with self.client.messages.stream(
                    model=config.CLAUDE_MODEL,
                    system=SYSTEM_PROMPT,
                    messages=messages,
                    tools=TOOL_SCHEMAS,
                    max_tokens=4096,
                ) as stream:
                    for text in stream.text_stream:
                        full_text += text
                        yield {"type": "text", "text": text}

                deduped_sources = _dedup(sources)

                # 写入缓存和历史
                if self.cache is not None:
                    self.cache.set(user_message, full_text, deduped_sources)
                if self.history_manager is not None:
                    self.history_manager.add_assistant(full_text)

                yield {"type": "done", "sources": deduped_sources}
                return
            except Exception as e:
                yield {"type": "error", "message": str(e)}
                return

        yield {"type": "error", "message": "超出最大工具调用轮次"}

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
