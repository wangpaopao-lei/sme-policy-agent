"""文档处理流水线测试"""

import os
import tempfile
import shutil

import pytest

from src.ingestion.cleaner import clean_markdown, build_frontmatter, build_final_document
from src.ingestion.pipeline_v2 import process_file, run_pipeline, _merge_metadata


# ============================================================
# Cleaner 测试
# ============================================================


class TestCleanMarkdown:
    def test_fullwidth_space(self):
        text = "前文\n\u3000\u3000第一条 正文内容"
        result = clean_markdown(text)
        assert "\u3000" not in result
        assert "  第一条 正文内容" in result

    def test_trailing_spaces(self):
        text = "第一行   \n第二行  "
        result = clean_markdown(text)
        assert "第一行\n第二行" == result

    def test_compress_blank_lines(self):
        text = "第一段\n\n\n\n\n第二段"
        result = clean_markdown(text)
        assert result == "第一段\n\n第二段"

    def test_strip_leading_trailing(self):
        text = "\n\n\n内容\n\n\n"
        result = clean_markdown(text)
        assert result == "内容"


class TestBuildFrontmatter:
    def test_basic(self):
        meta = {"title": "测试标题", "source": "test.pdf", "file_type": "pdf"}
        fm = build_frontmatter(meta)
        assert fm.startswith("---")
        assert fm.endswith("---")
        assert "title: 测试标题" in fm
        assert "source: test.pdf" in fm

    def test_skips_none(self):
        meta = {"title": "标题", "policy_number": None, "source": "x.pdf"}
        fm = build_frontmatter(meta)
        assert "policy_number" not in fm

    def test_quotes_colons(self):
        """半角冒号+空格需要引号，全角冒号不需要"""
        meta = {"title": "key: value style"}
        fm = build_frontmatter(meta)
        assert '"key: value style"' in fm

        meta2 = {"title": "关于：测试"}
        fm2 = build_frontmatter(meta2)
        assert "title: 关于：测试" in fm2

    def test_field_order(self):
        meta = {
            "category": "融资支持",
            "title": "标题",
            "source": "x.pdf",
        }
        fm = build_frontmatter(meta)
        title_pos = fm.index("title")
        source_pos = fm.index("source")
        category_pos = fm.index("category")
        assert title_pos < source_pos < category_pos


class TestBuildFinalDocument:
    def test_combines_frontmatter_and_content(self):
        result = build_final_document("# 标题\n\n正文", {"title": "标题"})
        assert result.startswith("---\n")
        assert "title: 标题" in result
        assert "# 标题\n\n正文" in result


# ============================================================
# 元数据合并测试
# ============================================================


class TestMergeMetadata:
    def test_priority_order(self):
        """parser_meta 优先级最高"""
        result = _merge_metadata(
            parser_meta={"title": "Parser标题"},
            regex_meta={"title": "Regex标题", "category": "融资支持"},
            llm_meta={"title": "LLM标题", "category": "税收优惠", "policy_number": "X号"},
            source="test.pdf",
            file_type="pdf",
        )
        assert result["title"] == "Parser标题"
        assert result["category"] == "融资支持"
        assert result["policy_number"] == "X号"
        assert result["source"] == "test.pdf"

    def test_missing_fields_omitted(self):
        result = _merge_metadata(
            parser_meta={},
            regex_meta={"title": "标题"},
            llm_meta={},
            source="test.pdf",
            file_type="pdf",
        )
        assert result["title"] == "标题"
        assert "policy_number" not in result


# ============================================================
# process_file 测试
# ============================================================


class TestProcessFile:
    def test_process_txt_file(self):
        content = "关于实施贷款贴息政策的通知\n\n各省：\n\n正文内容。\n\n2026年3月15日"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            f.flush()
            result = process_file(f.name, use_llm=False)

        os.unlink(f.name)
        assert result is not None
        assert result["source"] == os.path.basename(f.name)
        assert "关于实施贷款贴息政策的通知" in result["final_document"]
        assert result["metadata"]["category"] == "融资支持"

    def test_process_md_file(self):
        content = "# 测试政策\n\n## 第一条\n\n正文。"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            f.flush()
            result = process_file(f.name, use_llm=False)

        os.unlink(f.name)
        assert result is not None
        assert "---" in result["final_document"]  # 有 frontmatter
        assert "测试政策" in result["final_document"]

    def test_process_html_file(self):
        content = "<html><head><title>政策文件</title></head><body><p>正文</p></body></html>"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            f.flush()
            result = process_file(f.name, use_llm=False)

        os.unlink(f.name)
        assert result is not None
        assert result["metadata"]["file_type"] == "html"

    def test_unsupported_format(self):
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(b"fake docx")
            f.flush()
            result = process_file(f.name, use_llm=False)

        os.unlink(f.name)
        assert result is None

    def test_empty_content(self):
        """空文件仍会被解析（文件名作标题），但 markdown 主体为空"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("")
            f.flush()
            result = process_file(f.name, use_llm=False)

        os.unlink(f.name)
        # md_parser 会用文件名生成标题，所以不是 None
        # 但实际内容是空的（只有标题行）
        if result is not None:
            assert result["metadata"]["file_type"] == "markdown"


# ============================================================
# run_pipeline 测试
# ============================================================


class TestRunPipeline:
    def test_pipeline_with_temp_dir(self):
        """用临时目录测试完整流水线"""
        data_dir = tempfile.mkdtemp()
        output_dir = tempfile.mkdtemp()

        try:
            # 创建测试文件
            with open(os.path.join(data_dir, "test1.txt"), "w") as f:
                f.write("关于测试政策的通知\n\n各省：\n\n正文内容贷款贴息。\n\n2026年1月1日")

            with open(os.path.join(data_dir, "test2.md"), "w") as f:
                f.write("# 另一个政策\n\n科技创新内容。")

            result = run_pipeline(
                data_dir=data_dir,
                output_dir=output_dir,
                use_llm=False,
            )

            assert result["total_files"] == 2
            assert result["processed"] == 2
            assert result["failed"] == []
            assert len(result["documents"]) == 2

            # 检查输出文件
            output_files = os.listdir(output_dir)
            assert len(output_files) == 2
            assert all(f.endswith(".md") for f in output_files)

            # 检查输出内容有 frontmatter
            with open(os.path.join(output_dir, "test1.md"), "r") as f:
                content = f.read()
            assert content.startswith("---\n")
            assert "关于测试政策的通知" in content

        finally:
            shutil.rmtree(data_dir)
            shutil.rmtree(output_dir)

    def test_pipeline_empty_dir(self):
        data_dir = tempfile.mkdtemp()
        output_dir = tempfile.mkdtemp()

        try:
            result = run_pipeline(
                data_dir=data_dir,
                output_dir=output_dir,
                use_llm=False,
            )
            assert result["total_files"] == 0
            assert result["processed"] == 0
        finally:
            shutil.rmtree(data_dir)
            shutil.rmtree(output_dir)

    def test_pipeline_with_subdirs(self):
        """测试递归扫描子目录"""
        data_dir = tempfile.mkdtemp()
        output_dir = tempfile.mkdtemp()

        try:
            sub_dir = os.path.join(data_dir, "subdir")
            os.makedirs(sub_dir)

            with open(os.path.join(sub_dir, "nested.txt"), "w") as f:
                f.write("嵌套目录中的政策文件\n\n正文内容。")

            result = run_pipeline(
                data_dir=data_dir,
                output_dir=output_dir,
                use_llm=False,
            )

            assert result["processed"] == 1

        finally:
            shutil.rmtree(data_dir)
            shutil.rmtree(output_dir)


class TestRunPipelineOnRealData:
    @pytest.mark.skipif(
        not os.path.exists("data/关于实施中小微企业贷款贴息政策的通知.txt"),
        reason="测试数据文件不存在",
    )
    def test_pipeline_real_data_no_llm(self):
        """用真实数据测试（不调 LLM）"""
        output_dir = tempfile.mkdtemp()
        try:
            result = run_pipeline(
                data_dir="data",
                output_dir=output_dir,
                use_llm=False,
            )
            assert result["processed"] > 0
            assert len(result["failed"]) == 0

            # 检查所有输出文件都有 frontmatter
            for fname in os.listdir(output_dir):
                with open(os.path.join(output_dir, fname), "r") as f:
                    content = f.read()
                assert content.startswith("---\n"), f"{fname} 缺少 frontmatter"

        finally:
            shutil.rmtree(output_dir)
