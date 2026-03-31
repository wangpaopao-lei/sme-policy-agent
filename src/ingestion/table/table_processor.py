"""表格处理器

将解析器提取的表格转为自然语言描述，并通过 LLM 生成检索用的
Questions（用于向量检索）和加权 Keywords（用于 BM25 检索）。
"""

import json
import re

import anthropic

import config


GENERATE_QK_PROMPT = """你是一个政策文档分析专家。以下是从政策文档中提取的表格内容及其上下文。

请生成：
1. questions：3-5个用户可能会问的问题（口语化，像真实用户提问）
2. keywords：关键词及其权重（用于搜索索引）

关键词权重规则：
- 权重5：核心概念（政策名称、政策类型）
- 权重4：关键数据（具体数字、比例、金额、日期）
- 权重3：实体（企业类型、机关名称、行业名称）
- 权重2：一般关键词

要求：
- questions 要覆盖表格中的主要信息点
- keywords 不超过15个
- 只返回 JSON，不要其他文字

文档标题：{title}
表格所在章节：{section_context}

表格内容：
{table_content}

返回格式：
{{"questions": ["问题1", "问题2", ...], "keywords": {{"关键词1": 5, "关键词2": 3, ...}}}}"""


def table_to_natural_language(table_markdown: str) -> str:
    """
    将 Markdown 表格转为自然语言描述。

    单列表格（专栏类）：已经是自然语言，只做简单清理。
    多列表格：逐行转为自然语言句子。
    """
    lines = table_markdown.strip().splitlines()

    # 引用块格式（单列专栏，由 pdf_parser 转换）
    if lines[0].startswith("> "):
        # 去掉引用标记，保留原文
        text = "\n".join(line.lstrip("> ").strip() for line in lines if line.strip())
        return text

    # 多列 Markdown 表格
    # 提取表头和数据行
    table_lines = [l for l in lines if l.strip().startswith("|")]
    if len(table_lines) < 3:  # 至少需要表头+分隔符+一行数据
        return table_markdown  # 无法解析，返回原文

    # 解析表头
    header_cells = [c.strip() for c in table_lines[0].split("|") if c.strip()]

    # 跳过分隔行（第二行），解析数据行
    sentences = []
    for row_line in table_lines[2:]:
        cells = [c.strip() for c in row_line.split("|") if c.strip()]
        if not cells:
            continue

        # 将每行数据转为自然语言
        # 如：["小型企业", "2%", "500万"] + ["企业类型", "贴息比例", "最高额度"]
        # → "小型企业的贴息比例为2%，最高额度为500万"
        parts = []
        for i, cell in enumerate(cells):
            if i < len(header_cells) and cell:
                parts.append(f"{header_cells[i]}为{cell}")

        if parts:
            sentence = "，".join(parts) + "。"
            sentences.append(sentence)

    return "\n".join(sentences) if sentences else table_markdown


def _extract_section_context(table_markdown: str, full_markdown: str) -> str:
    """提取表格所在的章节上下文（表格前的最近标题）"""
    if not full_markdown:
        return ""

    # 找到表格在全文中的位置
    # 对于引用块表格，用前几个字匹配
    table_start = table_markdown[:50].strip().replace("> ", "")
    pos = full_markdown.find(table_start)
    if pos == -1:
        return ""

    # 往前找最近的标题
    before_text = full_markdown[:pos]
    headings = re.findall(r"^(#{1,4}\s+.+)$", before_text, re.MULTILINE)
    if headings:
        return headings[-1].lstrip("# ").strip()

    return ""


def generate_questions_and_keywords(
    table_content: str,
    title: str = "",
    section_context: str = "",
    client: anthropic.Anthropic | None = None,
) -> dict:
    """
    用 LLM 为表格生成检索用的 Questions 和加权 Keywords。

    参数:
        table_content: 表格的自然语言描述
        title: 文档标题
        section_context: 表格所在章节
        client: Anthropic 客户端（可选，用于测试注入）

    返回:
    {
        "questions": list[str],
        "keywords": dict[str, int]
    }
    """
    if client is None:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    prompt = GENERATE_QK_PROMPT.format(
        title=title or "未知",
        section_context=section_context or "未知",
        table_content=table_content[:2000],  # 限制长度控制成本
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = response.content[0].text.strip()

    # 解析 JSON
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0].strip()
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0].strip()

    try:
        result = json.loads(response_text)
    except json.JSONDecodeError:
        return {"questions": [], "keywords": {}}

    return {
        "questions": result.get("questions", []),
        "keywords": result.get("keywords", {}),
    }


def process_table(
    table_markdown: str,
    title: str = "",
    full_markdown: str = "",
    client: anthropic.Anthropic | None = None,
) -> dict:
    """
    处理单个表格：生成自然语言描述、Questions、Keywords。

    参数:
        table_markdown: Markdown 格式表格（或引用块）
        title: 文档标题
        full_markdown: 文档完整 Markdown（用于提取章节上下文）
        client: Anthropic 客户端（可选，用于测试注入）

    返回:
    {
        "markdown": str,                    # 原始 Markdown 表格
        "natural_language": str,            # 自然语言描述
        "questions": list[str],             # LLM 生成的检索问题
        "keywords": dict[str, int]          # 加权关键词
    }
    """
    natural_language = table_to_natural_language(table_markdown)
    section_context = _extract_section_context(table_markdown, full_markdown)

    qk = generate_questions_and_keywords(
        table_content=natural_language,
        title=title,
        section_context=section_context,
        client=client,
    )

    return {
        "markdown": table_markdown,
        "natural_language": natural_language,
        "questions": qk["questions"],
        "keywords": qk["keywords"],
    }


def process_tables(
    tables: list[dict],
    title: str = "",
    full_markdown: str = "",
    client: anthropic.Anthropic | None = None,
) -> list[dict]:
    """
    批量处理文档中的所有表格。

    参数:
        tables: parser 返回的表格列表 [{"markdown": str, "page": int}]
        title: 文档标题
        full_markdown: 文档完整 Markdown
        client: Anthropic 客户端

    返回: 处理后的表格列表
    """
    results = []
    for table in tables:
        result = process_table(
            table_markdown=table["markdown"],
            title=title,
            full_markdown=full_markdown,
            client=client,
        )
        result["page"] = table.get("page", 0)
        results.append(result)
    return results
