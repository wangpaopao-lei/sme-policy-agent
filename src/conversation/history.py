"""对话历史管理

滑动窗口保留最近 N 轮对话，供 Claude API 使用。
"""


class ConversationHistory:
    """滑动窗口对话历史"""

    def __init__(self, max_rounds: int = 10):
        """
        参数:
            max_rounds: 保留的最大对话轮数（一问一答 = 一轮）
        """
        self.max_rounds = max_rounds
        self._messages: list[dict] = []

    def add_user(self, content: str) -> None:
        """添加用户消息"""
        self._messages.append({"role": "user", "content": content})
        self._trim()

    def add_assistant(self, content: str) -> None:
        """添加助手消息"""
        self._messages.append({"role": "assistant", "content": content})
        self._trim()

    def _trim(self) -> None:
        """裁剪到最近 max_rounds 轮"""
        # 一轮 = 2 条消息（user + assistant）
        max_messages = self.max_rounds * 2
        if len(self._messages) > max_messages:
            self._messages = self._messages[-max_messages:]
            # 确保第一条是 user（Claude API 要求）
            if self._messages and self._messages[0]["role"] == "assistant":
                self._messages = self._messages[1:]

    def get_messages(self) -> list[dict]:
        """获取当前历史消息列表（用于传给 Claude API）"""
        return list(self._messages)

    def get_recent_context(self, n_rounds: int = 3) -> str:
        """
        获取最近 N 轮对话的文本摘要（用于 query 改写）。

        返回格式：
        用户: xxx
        助手: xxx
        用户: xxx
        助手: xxx
        """
        recent = self._messages[-(n_rounds * 2):]
        lines = []
        for msg in recent:
            role = "用户" if msg["role"] == "user" else "助手"
            # 截断过长的消息
            content = msg["content"][:200]
            if len(msg["content"]) > 200:
                content += "..."
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def clear(self) -> None:
        """清空历史"""
        self._messages = []

    def __len__(self) -> int:
        """返回消息条数"""
        return len(self._messages)
