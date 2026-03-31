"""文档清洗与格式化

负责 Markdown 输出前的最终清洗和 YAML frontmatter 生成。
"""

import re


def clean_markdown(markdown: str) -> str:
    """
    最终清洗 Markdown 文本。

    - 全角空格转半角
    - 去除行尾空格
    - 压缩连续空行（最多保留2个换行）
    - 去除开头/结尾多余空行
    """
    # 全角空格转半角
    markdown = markdown.replace("\u3000", " ")

    # 去除每行行尾空格
    lines = [line.rstrip() for line in markdown.splitlines()]
    markdown = "\n".join(lines)

    # 压缩连续空行
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)

    # 去除开头结尾空行
    markdown = markdown.strip()

    return markdown


def build_frontmatter(metadata: dict) -> str:
    """
    将元数据构建为 YAML frontmatter 格式。

    只输出有值的字段，None 值跳过。
    """
    lines = ["---"]

    # 按固定顺序输出
    field_order = [
        "title",
        "source",
        "file_type",
        "policy_number",
        "issuing_authority",
        "publish_date",
        "effective_date",
        "expiry_date",
        "applicable_region",
        "category",
    ]

    for field in field_order:
        value = metadata.get(field)
        if value is not None:
            # YAML 中含冒号或特殊字符的值需要引号
            if isinstance(value, str) and (": " in value or '"' in value or "'" in value):
                value_str = f'"{value}"'
            else:
                value_str = str(value)
            lines.append(f"{field}: {value_str}")

    lines.append("---")
    return "\n".join(lines)


def build_final_document(markdown: str, metadata: dict) -> str:
    """
    组合 frontmatter + markdown → 最终输出文档。
    """
    frontmatter = build_frontmatter(metadata)
    cleaned = clean_markdown(markdown)
    return f"{frontmatter}\n\n{cleaned}\n"
