"""PDF 文档解析器

使用 pdfplumber 提取文本和表格，输出结构化 Markdown。
对于政策文档中常见的"专栏"类表格和多列数据表格均做处理。
"""

import re
from pathlib import Path

import pdfplumber


def _extract_title(first_page_text: str, file_path: str) -> str:
    """从首页文本提取标题，fallback 到文件名"""
    if first_page_text:
        lines = [l.strip() for l in first_page_text.strip().splitlines() if l.strip()]
        if lines:
            return lines[0]
    return Path(file_path).stem


def _table_to_markdown(table: list[list]) -> str:
    """将 pdfplumber 提取的表格转为 Markdown 格式"""
    if not table or not table[0]:
        return ""

    # 清理单元格：None → 空字符串，去除首尾空白
    cleaned = []
    for row in table:
        cleaned.append([str(cell).strip() if cell is not None else "" for cell in row])

    num_cols = max(len(row) for row in cleaned)

    # 补齐列数不一致的行
    for row in cleaned:
        while len(row) < num_cols:
            row.append("")

    # 单列表格（政策文档中的"专栏"类型）：转为引用块
    if num_cols == 1:
        lines = []
        for row in cleaned:
            text = row[0].replace("\n", "\n> ")
            if text:
                lines.append(f"> {text}")
        return "\n>\n".join(lines)

    # 多列表格：标准 Markdown 表格
    lines = []
    # 表头
    header = "| " + " | ".join(cleaned[0]) + " |"
    separator = "| " + " | ".join(["---"] * num_cols) + " |"
    lines.append(header)
    lines.append(separator)

    # 数据行
    for row in cleaned[1:]:
        # 单元格内换行替换为空格
        cells = [cell.replace("\n", " ") for cell in row]
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)


def _is_header_by_font(chars: list[dict], line_text: str, page_chars: list[dict]) -> bool:
    """根据字符大小判断是否为标题行（比正文大）"""
    if not chars or not page_chars:
        return False

    # 计算该行的平均字号
    line_sizes = [c.get("size", 0) for c in chars if c.get("text", "").strip()]
    if not line_sizes:
        return False
    avg_line_size = sum(line_sizes) / len(line_sizes)

    # 计算全页的中位字号（作为正文基准）
    all_sizes = [c.get("size", 0) for c in page_chars if c.get("text", "").strip()]
    if not all_sizes:
        return False
    all_sizes.sort()
    median_size = all_sizes[len(all_sizes) // 2]

    return avg_line_size > median_size * 1.15


def _build_markdown_from_page(page) -> tuple[str, list[str]]:
    """从单页提取文本，尝试识别标题层级，返回 (markdown文本, 表格markdown列表)"""
    text = page.extract_text() or ""
    tables = page.extract_tables()
    table_markdowns = []

    if tables:
        for table in tables:
            md = _table_to_markdown(table)
            if md:
                table_markdowns.append(md)

    return text, table_markdowns


def _text_to_markdown(full_text: str) -> str:
    """将 PDF 提取的纯文本转换为 Markdown，识别政策文档中的结构"""
    lines = full_text.splitlines()
    md_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            md_lines.append("")
            continue

        # 去除页码（单独的数字行）
        if re.match(r'^\d{1,3}$', stripped):
            continue

        # 识别章标题：第X章
        if re.match(r'^第[一二三四五六七八九十百]+章\s', stripped):
            md_lines.append(f"\n## {stripped}")
            continue

        # 识别条标题：第X条
        if re.match(r'^第[一二三四五六七八九十百]+条\s', stripped):
            md_lines.append(f"\n### {stripped}")
            continue

        # 识别大节标题：一、二、三、
        if re.match(r'^[一二三四五六七八九十]+[、.]\s*\S', stripped):
            md_lines.append(f"\n#### {stripped}")
            continue

        # 识别子项：（一）（二）
        if re.match(r'^（[一二三四五六七八九十]+）', stripped):
            md_lines.append(f"\n- {stripped}")
            continue

        # 识别数字子项：1. 2. 或 1、2、
        if re.match(r'^\d+[、.．]\s*\S', stripped):
            md_lines.append(f"- {stripped}")
            continue

        md_lines.append(stripped)

    return "\n".join(md_lines)


def parse_pdf(file_path: str) -> dict:
    """
    解析 PDF 文件，提取文本和表格，输出结构化 Markdown。

    返回:
    {
        "markdown": str,           # 结构化 Markdown 文本
        "tables": list[dict],      # 提取的表格
        "raw_text": str,           # 原始纯文本（用于元数据提取）
        "source": str,             # 文件名
        "file_type": "pdf"
    }
    """
    all_text_parts = []
    all_tables = []

    with pdfplumber.open(file_path) as pdf:
        first_page_text = ""

        for i, page in enumerate(pdf.pages):
            page_text, table_markdowns = _build_markdown_from_page(page)

            if i == 0:
                first_page_text = page_text

            if page_text:
                all_text_parts.append(page_text)

            for t_md in table_markdowns:
                all_tables.append({
                    "markdown": t_md,
                    "page": i + 1,
                })

    raw_text = "\n".join(all_text_parts)
    title = _extract_title(first_page_text, file_path)
    markdown = _text_to_markdown(raw_text)

    # 在 Markdown 开头添加文档标题
    markdown = f"# {title}\n\n{markdown}"

    return {
        "markdown": markdown,
        "tables": all_tables,
        "raw_text": raw_text,
        "source": Path(file_path).name,
        "title": title,
        "file_type": "pdf",
    }
