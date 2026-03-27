import json

# ── 工具 Schema（提供给 Claude）────────────────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "name": "search_policy",
        "description": (
            "根据用户问题语义检索最相关的政策片段。"
            "当需要了解某类政策内容、政策要求或政策细节时使用。"
            "可以多次调用，使用不同关键词从不同角度检索。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "检索关键词或问题描述，建议使用政策领域的专业词汇",
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回的结果数量，默认 5，最多 10",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_policy_detail",
        "description": (
            "获取某篇政策文件的完整内容。"
            "当 search_policy 返回了相关文件名，需要深入了解该文件全文时使用。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "政策文件的文件名，来自 search_policy 结果中的 source 字段",
                },
            },
            "required": ["source"],
        },
    },
]


# ── 工具执行逻辑 ───────────────────────────────────────────────────────────────

def execute_search_policy(query: str, top_k: int, embedder, store) -> str:
    """执行语义检索，返回格式化的结果字符串供 Claude 阅读"""
    top_k = min(max(1, top_k), 10)
    query_vec = embedder.embed(query)
    chunks = store.query(query_vec, top_k=top_k)

    if not chunks:
        return "未找到相关政策内容。"

    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(
            f"[片段 {i}]\n"
            f"来源文件：{chunk['source']}\n"
            f"文件标题：{chunk['title']}\n"
            f"相关度：{chunk['score']}\n"
            f"内容：\n{chunk['text']}\n"
        )
    return "\n---\n".join(parts)


def execute_get_policy_detail(source: str, store) -> str:
    """获取某文件全部 chunks，拼接为完整内容供 Claude 阅读"""
    chunks = store.get_by_source(source)

    if not chunks:
        return f"未找到文件：{source}"

    title = chunks[0]["title"]
    full_text = "\n".join(c["text"] for c in chunks)

    return f"文件名：{source}\n标题：{title}\n\n全文内容：\n{full_text}"


def execute_tool(name: str, tool_input: dict, embedder, store) -> str:
    """统一工具调度入口"""
    if name == "search_policy":
        return execute_search_policy(
            query=tool_input["query"],
            top_k=tool_input.get("top_k", 5),
            embedder=embedder,
            store=store,
        )
    elif name == "get_policy_detail":
        return execute_get_policy_detail(
            source=tool_input["source"],
            store=store,
        )
    else:
        return f"未知工具：{name}"
