"""Query 改写器

多轮对话中，用户的后续提问常包含指代和省略：
  "它的贴息比例是多少" → 需要结合上文改写为完整查询

使用 Claude Haiku 进行改写，成本低、速度快。
"""

import anthropic

import config


REWRITE_PROMPT = """你是一个查询改写助手。根据对话历史，将用户的最新问题改写为一个完整、独立、适合搜索的查询。

规则：
- 补全指代词（它、这个、该政策 → 具体名称）
- 补全省略的主语或宾语
- 保持原意，不添加额外信息
- 如果问题本身已经完整，直接返回原问题
- 只返回改写后的查询，不要解释

对话历史：
{history}

用户最新问题：{query}

改写后的查询："""


class QueryRewriter:
    """基于 Claude 的 Query 改写器"""

    def __init__(self, client: anthropic.Anthropic | None = None):
        if client is None:
            client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.client = client

    def rewrite(self, query: str, history_context: str) -> str:
        """
        结合对话历史改写 query。

        参数:
            query: 用户当前问题
            history_context: 对话历史文本（由 ConversationHistory.get_recent_context 生成）

        返回: 改写后的查询（如果不需要改写则返回原 query）
        """
        # 没有历史时不需要改写
        if not history_context.strip():
            return query

        # 简单启发式：如果问题不含指代词/省略，可能不需要改写
        needs_rewrite = any(kw in query for kw in [
            "它", "这个", "该", "那个", "上面", "前面", "刚才",
            "还有", "另外", "其他", "比较", "对比", "区别",
            "多少", "怎么", "什么时候",  # 可能省略了主语
        ])

        # 短问题也可能需要改写（省略了上下文）
        if len(query) < 10:
            needs_rewrite = True

        if not needs_rewrite:
            return query

        prompt = REWRITE_PROMPT.format(
            history=history_context,
            query=query,
        )

        try:
            response = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=128,
                messages=[{"role": "user", "content": prompt}],
            )
            rewritten = response.content[0].text.strip()

            # 安全检查：改写结果不应该太长或太短
            if len(rewritten) < 2 or len(rewritten) > len(query) * 5:
                return query

            return rewritten
        except Exception:
            # LLM 调用失败时返回原 query
            return query
