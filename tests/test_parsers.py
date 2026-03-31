"""文档解析器测试"""

import os
import tempfile
import pytest

from src.ingestion.parsers.pdf_parser import parse_pdf, _table_to_markdown, _text_to_markdown
from src.ingestion.parsers.html_parser import parse_html, _is_layout_table, _clean_noise_lines
from src.ingestion.parsers.md_parser import parse_markdown


# ============================================================
# PDF Parser 测试
# ============================================================


class TestPdfTableToMarkdown:
    def test_multi_column_table(self):
        table = [
            ["企业类型", "贴息比例", "最高额度"],
            ["小型企业", "2%", "500万"],
            ["微型企业", "2.5%", "200万"],
        ]
        md = _table_to_markdown(table)
        assert "| 企业类型 | 贴息比例 | 最高额度 |" in md
        assert "| --- | --- | --- |" in md
        assert "| 小型企业 | 2% | 500万 |" in md

    def test_single_column_table_to_blockquote(self):
        """单列表格（专栏类型）应转为引用块"""
        table = [
            ["专栏 1 技术提升工程"],
            ["1.重点方向一\n2.重点方向二"],
        ]
        md = _table_to_markdown(table)
        assert md.startswith("> ")
        assert "专栏 1 技术提升工程" in md

    def test_none_cells(self):
        table = [["标题", None], ["内容", "数据"]]
        md = _table_to_markdown(table)
        assert "| 标题 |  |" in md
        assert "| 内容 | 数据 |" in md

    def test_empty_table(self):
        assert _table_to_markdown([]) == ""
        assert _table_to_markdown([[]]) == ""


class TestPdfTextToMarkdown:
    def test_chapter_heading(self):
        text = "第一章 总则"
        md = _text_to_markdown(text)
        assert "## 第一章 总则" in md

    def test_article_heading(self):
        text = "第三条 申请条件"
        md = _text_to_markdown(text)
        assert "### 第三条 申请条件" in md

    def test_section_heading(self):
        text = "一、政策内容"
        md = _text_to_markdown(text)
        assert "#### 一、政策内容" in md

    def test_sub_items(self):
        text = "（一）适用对象\n（二）投向领域"
        md = _text_to_markdown(text)
        assert "- （一）适用对象" in md
        assert "- （二）投向领域" in md

    def test_numbered_items(self):
        text = "1.重点方向一\n2.重点方向二"
        md = _text_to_markdown(text)
        assert "- 1.重点方向一" in md

    def test_page_number_removed(self):
        text = "正文内容\n5\n下一段"
        md = _text_to_markdown(text)
        assert "\n5\n" not in md


class TestParsePdf:
    @pytest.mark.skipif(
        not os.path.exists("data/优质中小企业梯度培育管理办法(1).pdf"),
        reason="测试数据文件不存在",
    )
    def test_parse_real_pdf(self):
        result = parse_pdf("data/优质中小企业梯度培育管理办法(1).pdf")
        assert result["file_type"] == "pdf"
        assert result["title"] == "优质中小企业梯度培育管理办法"
        assert result["source"] == "优质中小企业梯度培育管理办法(1).pdf"
        assert result["markdown"].startswith("# ")
        assert "## 第一章 总则" in result["markdown"]
        assert "### 第一条" in result["markdown"]
        assert len(result["raw_text"]) > 0

    @pytest.mark.skipif(
        not os.path.exists("data/《茶产业提质升级指导意见（2026—2030年）》.pdf"),
        reason="测试数据文件不存在",
    )
    def test_parse_pdf_with_tables(self):
        result = parse_pdf("data/《茶产业提质升级指导意见（2026—2030年）》.pdf")
        assert len(result["tables"]) > 0
        # 专栏表格应被转为引用块
        assert any(">" in t["markdown"] for t in result["tables"])


# ============================================================
# HTML Parser 测试
# ============================================================


class TestHtmlCleanNoise:
    def test_removes_login_register(self):
        text = "登录 | 注册\n\n正文内容"
        cleaned = _clean_noise_lines(text)
        assert "登录" not in cleaned
        assert "正文内容" in cleaned

    def test_removes_navigation(self):
        text = "首页Home\n政策文件库\n易找 易懂\n正文"
        cleaned = _clean_noise_lines(text)
        assert "首页" not in cleaned
        assert "正文" in cleaned

    def test_preserves_content(self):
        text = "第一条 总则\n本办法适用于中小企业"
        cleaned = _clean_noise_lines(text)
        assert text == cleaned


class TestHtmlIsLayoutTable:
    def test_data_table_with_th(self):
        from bs4 import BeautifulSoup
        html = "<table><tr><th>类型</th><th>比例</th></tr><tr><td>小型</td><td>2%</td></tr></table>"
        soup = BeautifulSoup(html, "lxml")
        assert not _is_layout_table(soup.find("table"))

    def test_layout_table_long_content(self):
        from bs4 import BeautifulSoup
        long_text = "这是一段很长的文本" * 30
        html = f"<table><tr><td>{long_text}</td></tr></table>"
        soup = BeautifulSoup(html, "lxml")
        assert _is_layout_table(soup.find("table"))


class TestParseHtml:
    def test_basic_html(self):
        html_content = """
        <html>
        <head><title>测试政策</title></head>
        <body>
            <h1>测试政策文件</h1>
            <p>第一条 这是正文内容。</p>
        </body>
        </html>
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
            f.write(html_content)
            f.flush()
            result = parse_html(f.name)

        os.unlink(f.name)
        assert result["file_type"] == "html"
        assert "测试政策" in result["title"]
        assert "正文内容" in result["markdown"]

    def test_meta_tags_extraction(self):
        html_content = """
        <html>
        <head>
            <title>政策文件</title>
            <meta name="keywords" content="中小企业,贷款">
            <meta name="publishdate" content="2024-03-15">
        </head>
        <body><p>内容</p></body>
        </html>
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
            f.write(html_content)
            f.flush()
            result = parse_html(f.name)

        os.unlink(f.name)
        assert result["meta_tags"]["keywords"] == "中小企业,贷款"
        assert result["meta_tags"]["publish_date"] == "2024-03-15"

    def test_noise_tags_removed(self):
        html_content = """
        <html><body>
            <nav>导航栏</nav>
            <p>正文内容</p>
            <footer>页脚</footer>
            <script>var x = 1;</script>
        </body></html>
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
            f.write(html_content)
            f.flush()
            result = parse_html(f.name)

        os.unlink(f.name)
        assert "导航栏" not in result["markdown"]
        assert "页脚" not in result["markdown"]
        assert "var x" not in result["markdown"]
        assert "正文内容" in result["markdown"]


# ============================================================
# Markdown / TXT Parser 测试
# ============================================================


class TestParseMarkdown:
    def test_basic_markdown(self):
        content = "# 测试标题\n\n这是正文内容。\n\n## 第一节\n\n详细说明。"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            f.flush()
            result = parse_markdown(f.name)

        os.unlink(f.name)
        assert result["file_type"] == "markdown"
        assert result["title"] == "测试标题"
        assert "正文内容" in result["markdown"]

    def test_noise_removal(self):
        content = "登录 | 注册\n首页Home\n政策文件库\n\n关于贷款政策的通知\n\n正文内容"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(content)
            f.flush()
            result = parse_markdown(f.name)

        os.unlink(f.name)
        assert "登录" not in result["markdown"]
        assert "首页Home" not in result["markdown"]
        assert "关于贷款政策的通知" in result["title"]

    def test_bold_to_heading(self):
        content = "**一、政策内容**\n\n正文"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            f.flush()
            result = parse_markdown(f.name)

        os.unlink(f.name)
        assert "#### 一、政策内容" in result["markdown"]

    def test_publish_source_extraction(self):
        content = "标题\n发布来源:财政部\n\n正文"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(content)
            f.flush()
            result = parse_markdown(f.name)

        os.unlink(f.name)
        assert result["meta_tags"]["publish_source"] == "财政部"

    @pytest.mark.skipif(
        not os.path.exists("data/关于实施中小微企业贷款贴息政策的通知.txt"),
        reason="测试数据文件不存在",
    )
    def test_parse_real_txt(self):
        result = parse_markdown("data/关于实施中小微企业贷款贴息政策的通知.txt")
        assert "关于实施中小微企业贷款贴息政策的通知" in result["title"]
        assert result["meta_tags"].get("publish_source") == "财政部"
        # 噪音应被清除
        assert "首页Home" not in result["markdown"]
        assert "政策文件库" not in result["markdown"]
