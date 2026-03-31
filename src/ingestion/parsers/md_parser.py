"""Markdown / TXT 文档解析器

处理 Markdown 文件和从政策网站抓取的 TXT 文件（本质上也是 Markdown 格式）。
主要工作是去除网站导航噪音和格式标准化。
"""

import re
from pathlib import Path


# 网站噪音文本模式（和 html_parser 保持一致）
NOISE_PATTERNS = [
    r"^登录\s*\|?\s*注册",
    r"^\d{4}年\d{1,2}月\d{1,2}日\s*星期",
    r"^首页\s*Home",
    r"^首页$",
    r"^Home$",
    r"^政策文件库",
    r"^政策申报",
    r"^政策宣贯",
    r"^政策汇编",
    r"^政策图谱",
    r"^政策传播",
    r"^搜索$",
    r"^易找\s*易懂",
    r"^便捷\s*易享",
    r"^汇编\s*聚焦",
    r"^数据\s*服务",
    r"^观点\s*监测",
    r"^政策\s*活动",
    r"^\s*\|\s*\|?\s*$",
    r"^首页.*政策详情",
    r"^请输入政策标题",
    r"^原文$",
    r"^!\[.*\]\(.*\)$",  # Markdown 图片语法
    r"^\[登录",  # 登录/注册链接
    r"^-\s*首页",
    r"^-\s*政策文件",
    r"^-\s*政策详情",
]


def _extract_title(text: str, file_path: str) -> str:
    """从文本中提取标题"""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]

    for line in lines:
        # 跳过噪音行
        is_noise = any(re.match(p, line) for p in NOISE_PATTERNS)
        if is_noise:
            continue

        # Markdown 标题
        if line.startswith("# "):
            return line.lstrip("# ").strip()

        # 第一个有意义的非空行
        # 跳过"发布来源"等元信息行
        if not re.match(r"^发布来源[:：]", line):
            return line

    return Path(file_path).stem


def _extract_publish_source(text: str) -> str | None:
    """从正文提取发布来源"""
    match = re.search(r"发布来源[:：]\s*(.+)", text)
    if match:
        return match.group(1).strip()
    return None


def _clean_noise(text: str) -> str:
    """清理网站导航噪音"""
    lines = text.splitlines()
    cleaned = []
    noise_compiled = [re.compile(p) for p in NOISE_PATTERNS]

    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue

        is_noise = any(p.match(stripped) for p in noise_compiled)
        if not is_noise:
            cleaned.append(line)

    # 去掉开头的连续空行
    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)

    return "\n".join(cleaned)


def _standardize_markdown(text: str) -> str:
    """标准化 Markdown 格式"""
    lines = text.splitlines()
    result = []

    for line in lines:
        stripped = line.strip()

        # 清除"发布来源"行（已提取为元数据）
        if re.match(r"^发布来源[:：]", stripped):
            continue

        # 把 **粗体标记的标题** 转为 Markdown 标题
        # 例：**一、政策内容** → #### 一、政策内容
        bold_match = re.match(r"^\s*\*\*([一二三四五六七八九十]+[、.].+?)\*\*\s*$", stripped)
        if bold_match:
            result.append(f"\n#### {bold_match.group(1)}")
            continue

        # 通用粗体行转标题（整行都是粗体的情况）
        bold_full = re.match(r"^\s*\*\*(.+?)\*\*\s*$", stripped)
        if bold_full:
            content = bold_full.group(1)
            # 检查是否像标题（短且不含标点句号）
            if len(content) < 50 and "。" not in content:
                result.append(f"\n### {content}")
                continue

        result.append(line)

    text = "\n".join(result)

    # 压缩多余空行
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text


def _extract_tables(markdown: str) -> list[dict]:
    """从 Markdown 中提取表格"""
    tables = []
    table_pattern = re.compile(r"(\|.+\|[\s\S]*?\|.+\|)", re.MULTILINE)
    for match in table_pattern.finditer(markdown):
        table_text = match.group(1).strip()
        if table_text.count("\n") >= 2:
            tables.append({"markdown": table_text, "page": 0})
    return tables


def parse_markdown(file_path: str) -> dict:
    """
    解析 Markdown 或 TXT 文件。

    返回:
    {
        "markdown": str,
        "tables": list[dict],
        "raw_text": str,
        "source": str,
        "title": str,
        "file_type": "markdown",
        "meta_tags": dict
    }
    """
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        raw_text = f.read()

    meta_tags = {}
    pub_source = _extract_publish_source(raw_text)
    if pub_source:
        meta_tags["publish_source"] = pub_source

    title = _extract_title(raw_text, file_path)

    # 清理噪音
    markdown = _clean_noise(raw_text)

    # 标准化格式
    markdown = _standardize_markdown(markdown)

    # 确保有标题
    if title and not markdown.strip().startswith(f"# {title}"):
        markdown = f"# {title}\n\n{markdown}"

    tables = _extract_tables(markdown)

    return {
        "markdown": markdown,
        "tables": tables,
        "raw_text": raw_text,
        "source": Path(file_path).name,
        "title": title,
        "file_type": "markdown",
        "meta_tags": meta_tags,
    }
