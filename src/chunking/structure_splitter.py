"""基于 Markdown 标题层级的语义分块

按文档的标题结构切割，保持语义完整性。
支持两种结构：
  - 章+条结构：## 第一章 → ### 第一条（如管理办法类）
  - 节结构：#### 一、 → 正文（如通知/意见类）
"""

import re


def _parse_sections(markdown: str) -> list[dict]:
    """
    将 Markdown 文本按标题切割成 section 列表。

    返回:
    [{
        "heading": str,        # 标题文本（不含 # 前缀）
        "level": int,          # 标题层级 (1-6)
        "content": str,        # 该 section 的完整文本（含标题行）
    }]
    """
    lines = markdown.splitlines()
    sections = []
    current_heading = ""
    current_level = 0
    current_lines = []

    for line in lines:
        heading_match = re.match(r'^(#{1,6})\s+(.+)', line)

        if heading_match:
            # 遇到新标题，保存之前的 section
            if current_lines:
                sections.append({
                    "heading": current_heading,
                    "level": current_level,
                    "content": "\n".join(current_lines),
                })

            current_level = len(heading_match.group(1))
            current_heading = heading_match.group(2).strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    # 最后一个 section
    if current_lines:
        sections.append({
            "heading": current_heading,
            "level": current_level,
            "content": "\n".join(current_lines),
        })

    return sections


def _get_split_level(sections: list[dict]) -> int:
    """
    自动判断应该按哪个标题层级切割。

    策略：
      - 跳过 H1（文档标题，只有一个）
      - 如果有 H2（章）且有 H3（条），按 H3 切割
      - 如果有 H4（一、二、三），按 H4 切割
      - 否则不切割，整篇作为一个 section
    """
    level_counts = {}
    for s in sections:
        if s["level"] > 0:
            level_counts[s["level"]] = level_counts.get(s["level"], 0) + 1

    # 跳过 H1
    level_counts.pop(1, None)

    if not level_counts:
        return 0  # 无子标题

    # 如果有 H3 且数量 >= 3，按 H3 切（章+条结构）
    if level_counts.get(3, 0) >= 3:
        return 3

    # 如果有 H4 且数量 >= 2，按 H4 切（节结构）
    if level_counts.get(4, 0) >= 2:
        return 4

    # 如果有 H2 且数量 >= 2，按 H2 切
    if level_counts.get(2, 0) >= 2:
        return 2

    # 返回数量最多的层级
    return max(level_counts, key=level_counts.get)


def split_by_structure(markdown: str, max_size: int = 1000) -> list[dict]:
    """
    基于 Markdown 标题层级分割文档。

    参数:
        markdown: 完整 Markdown 文本（含 frontmatter 则自动跳过）
        max_size: 单个 section 的最大字符数

    返回:
    [{
        "text": str,           # section 文本
        "heading": str,        # 所属标题
        "level": int,          # 标题层级
    }]
    """
    # 跳过 YAML frontmatter
    content = markdown
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3:].strip()

    sections = _parse_sections(content)

    if not sections:
        return [{"text": content, "heading": "", "level": 0}]

    split_level = _get_split_level(sections)

    if split_level == 0:
        # 无子标题，整篇作为一个 chunk
        return [{"text": content, "heading": sections[0]["heading"] if sections else "", "level": 0}]

    # 按 split_level 切割：该层级的每个标题开始一个新 chunk
    # 低于 split_level 的标题（如 H2 章标题）作为上下文前缀
    result = []
    parent_heading = ""
    current_text_parts = []
    current_heading = ""

    for section in sections:
        if section["level"] == 1:
            # H1 文档标题，跳过（不作为独立 chunk）
            continue

        if 0 < section["level"] < split_level:
            # 上级标题（如 H2 章标题），记为父标题
            # 如果之前有累积内容，先保存
            if current_text_parts:
                text = "\n".join(current_text_parts).strip()
                if text:
                    result.append({
                        "text": text,
                        "heading": current_heading,
                        "level": split_level,
                    })
                current_text_parts = []

            parent_heading = section["heading"]
            # 章标题本身也可能有内容
            content_without_heading = re.sub(r'^#{1,6}\s+.+\n?', '', section["content"]).strip()
            if content_without_heading:
                current_text_parts.append(section["content"])
                current_heading = parent_heading

        elif section["level"] == split_level:
            # 到达分割层级，保存之前的内容，开始新 chunk
            if current_text_parts:
                text = "\n".join(current_text_parts).strip()
                if text:
                    result.append({
                        "text": text,
                        "heading": current_heading,
                        "level": split_level,
                    })

            current_heading = section["heading"]
            if parent_heading:
                current_heading = f"{parent_heading} > {section['heading']}"

            current_text_parts = [section["content"]]

        else:
            # 更低层级的内容，附加到当前 chunk
            current_text_parts.append(section["content"])

    # 保存最后一个 chunk
    if current_text_parts:
        text = "\n".join(current_text_parts).strip()
        if text:
            result.append({
                "text": text,
                "heading": current_heading,
                "level": split_level,
            })

    # 如果切出来的某些 chunk 为空或结果为空，fallback
    if not result:
        return [{"text": content, "heading": "", "level": 0}]

    return result
