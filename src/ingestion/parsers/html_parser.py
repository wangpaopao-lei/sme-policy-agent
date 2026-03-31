"""HTML 文档解析器

使用 BeautifulSoup 清理噪音 + markdownify 转换为 Markdown。
针对政策网站（sme-service.cn 等）的页面结构做了噪音过滤。
"""

import re
from pathlib import Path

from bs4 import BeautifulSoup
import markdownify


# 需要移除的 HTML 标签（导航、脚注等噪音）
NOISE_TAGS = ["script", "style", "nav", "footer", "header", "aside", "iframe"]

# 网站噪音文本模式（从抓取的政策网页中常见的导航/菜单文本）
NOISE_PATTERNS = [
    r"^登录\s*\|?\s*注册",
    r"^\d{4}年\d{1,2}月\d{1,2}日\s*星期",
    r"^首页\s*Home",
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
    r"^\s*\|\s*$",
    r"^首页.*政策详情$",
    r"^请输入政策标题$",
    r"^原文$",
]


def _extract_meta_tags(soup: BeautifulSoup) -> dict:
    """提取 HTML meta 标签中的元数据"""
    meta = {}

    # title
    if soup.title and soup.title.string:
        meta["title"] = soup.title.string.strip()

    # meta 标签
    for tag in soup.find_all("meta"):
        name = tag.get("name", "").lower()
        content = tag.get("content", "").strip()
        if not content:
            continue
        if name in ("publishdate", "publish-date", "date"):
            meta["publish_date"] = content
        elif name in ("author", "source"):
            meta["author"] = content
        elif name == "keywords":
            meta["keywords"] = content
        elif name == "description":
            meta["description"] = content

    return meta


def _extract_title(soup: BeautifulSoup, meta_tags: dict) -> str:
    """提取标题：meta > <title> > <h1>"""
    if meta_tags.get("title"):
        return meta_tags["title"]
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return ""


def _remove_noise_tags(soup: BeautifulSoup) -> None:
    """移除噪音 HTML 标签"""
    for tag_name in NOISE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # 移除图片（政策文档中通常是 logo、装饰图）
    for img in soup.find_all("img"):
        img.decompose()


def _is_layout_table(table) -> bool:
    """判断表格是布局用还是数据用"""
    # 有 th 标签 → 大概率是数据表格
    if table.find("th"):
        return False

    rows = table.find_all("tr")
    if not rows:
        return True

    # 只有1列 → 可能是布局
    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) > 2:
            return False

    # 单元格内容很长 → 大概率是布局
    for cell in table.find_all("td"):
        if len(cell.get_text(strip=True)) > 200:
            return True

    return False


def _clean_noise_lines(text: str) -> str:
    """清理网站噪音文本行"""
    lines = text.splitlines()
    cleaned = []
    noise_compiled = [re.compile(p) for p in NOISE_PATTERNS]

    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue

        is_noise = False
        for pattern in noise_compiled:
            if pattern.match(stripped):
                is_noise = True
                break

        if not is_noise:
            cleaned.append(line)

    # 去掉开头的连续空行
    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)

    return "\n".join(cleaned)


def _extract_publish_source(text: str) -> str | None:
    """从正文提取发布来源"""
    match = re.search(r"发布来源[:：]\s*(.+)", text)
    if match:
        return match.group(1).strip()
    return None


def parse_html(file_path: str) -> dict:
    """
    解析 HTML 文件，清理噪音，转为 Markdown。

    返回:
    {
        "markdown": str,
        "tables": list[dict],
        "raw_text": str,
        "source": str,
        "title": str,
        "file_type": "html",
        "meta_tags": dict
    }
    """
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()

    soup = BeautifulSoup(html, "lxml")

    # 提取 meta 标签
    meta_tags = _extract_meta_tags(soup)
    title = _extract_title(soup, meta_tags)

    # 清理噪音标签
    _remove_noise_tags(soup)

    # 处理布局表格：提取内容但不保留表格格式
    for table in soup.find_all("table"):
        if _is_layout_table(table):
            # 用段落替换布局表格
            text = table.get_text(separator="\n", strip=True)
            table.replace_with(soup.new_string(text))

    # 提取原始文本（用于元数据提取）
    raw_text = soup.get_text(separator="\n")

    # 提取发布来源
    pub_source = _extract_publish_source(raw_text)
    if pub_source:
        meta_tags["publish_source"] = pub_source

    # 用 markdownify 转换
    # 获取 body 内容，没有 body 就用整个 soup
    body = soup.find("body") or soup
    markdown = markdownify.markdownify(
        str(body),
        heading_style="ATX",
        strip=["a"],  # 去掉链接（政策文档中的链接通常是导航）
    )

    # 清理噪音行
    markdown = _clean_noise_lines(markdown)

    # 清理多余空行（连续3个以上空行压缩为2个）
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)

    # 如果标题不在 Markdown 开头，补上
    if title and not markdown.startswith(f"# {title}"):
        markdown = f"# {title}\n\n{markdown}"

    # 提取表格（从 Markdown 中识别）
    tables = []
    table_pattern = re.compile(r"(\|.+\|[\s\S]*?\|.+\|)", re.MULTILINE)
    for match in table_pattern.finditer(markdown):
        table_text = match.group(1).strip()
        # 至少有表头+分隔+一行数据
        if table_text.count("\n") >= 2:
            tables.append({"markdown": table_text, "page": 0})

    return {
        "markdown": markdown,
        "tables": tables,
        "raw_text": raw_text,
        "source": Path(file_path).name,
        "title": title or Path(file_path).stem,
        "file_type": "html",
        "meta_tags": meta_tags,
    }
