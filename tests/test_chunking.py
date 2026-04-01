"""分块模块测试"""

import os
import pytest

from src.chunking.structure_splitter import (
    split_by_structure,
    _parse_sections,
    _get_split_level,
)
from src.chunking.fixed_splitter import split_fixed
from src.chunking.parent_child import (
    create_parent_child_chunks,
    _split_into_sub_sections,
    _make_id,
)


# ============================================================
# 结构化分块测试
# ============================================================


class TestParseSections:
    def test_basic_headings(self):
        md = "# 标题\n\n正文\n\n## 第一章\n\n内容1\n\n## 第二章\n\n内容2"
        sections = _parse_sections(md)
        assert len(sections) == 3
        assert sections[0]["level"] == 1
        assert sections[1]["heading"] == "第一章"
        assert sections[2]["heading"] == "第二章"

    def test_no_headings(self):
        md = "纯文本没有标题\n\n第二段"
        sections = _parse_sections(md)
        assert len(sections) == 1
        assert sections[0]["level"] == 0

    def test_nested_headings(self):
        md = "# 标题\n\n## 第一章\n\n### 第一条\n\n内容\n\n### 第二条\n\n内容2"
        sections = _parse_sections(md)
        assert len(sections) == 4
        assert sections[2]["level"] == 3
        assert sections[3]["level"] == 3


class TestGetSplitLevel:
    def test_chapter_article_structure(self):
        """章+条结构 → 按 H3 切"""
        sections = [
            {"level": 1, "heading": "标题"},
            {"level": 2, "heading": "第一章"},
            {"level": 3, "heading": "第一条"},
            {"level": 3, "heading": "第二条"},
            {"level": 3, "heading": "第三条"},
        ]
        assert _get_split_level(sections) == 3

    def test_section_structure(self):
        """节结构 → 按 H4 切"""
        sections = [
            {"level": 1, "heading": "标题"},
            {"level": 4, "heading": "一、总体要求"},
            {"level": 4, "heading": "二、主要任务"},
            {"level": 4, "heading": "三、保障措施"},
        ]
        assert _get_split_level(sections) == 4

    def test_no_sub_headings(self):
        """只有 H1 → 不切割"""
        sections = [{"level": 1, "heading": "标题"}]
        assert _get_split_level(sections) == 0


class TestSplitByStructure:
    def test_split_by_h4(self):
        md = "# 标题\n\n#### 一、第一节\n\n内容1\n\n#### 二、第二节\n\n内容2"
        result = split_by_structure(md)
        assert len(result) == 2
        assert "一、第一节" in result[0]["heading"]
        assert "二、第二节" in result[1]["heading"]

    def test_split_by_h3_with_h2_parent(self):
        md = "# 标题\n\n## 第一章 总则\n\n### 第一条\n\n内容1\n\n### 第二条\n\n内容2\n\n## 第二章\n\n### 第三条\n\n内容3"
        result = split_by_structure(md)
        assert len(result) >= 3
        # 第一条应包含父标题
        assert "第一章 总则" in result[0]["heading"]

    def test_no_sub_headings_returns_whole(self):
        md = "# 标题\n\n纯文本内容没有子标题。"
        result = split_by_structure(md)
        assert len(result) == 1

    def test_skips_frontmatter(self):
        md = "---\ntitle: 测试\n---\n\n# 标题\n\n#### 一、第一节\n\n内容"
        result = split_by_structure(md)
        assert "---" not in result[0]["text"]

    def test_empty_input(self):
        result = split_by_structure("")
        assert len(result) == 1


# ============================================================
# 固定长度分块测试
# ============================================================


class TestSplitFixed:
    def test_short_text_no_split(self):
        result = split_fixed("短文本", chunk_size=100)
        assert len(result) == 1

    def test_splits_by_paragraph(self):
        text = "段落1\n\n" + "段落2内容很长" * 50 + "\n\n段落3"
        result = split_fixed(text, chunk_size=200, overlap=50)
        assert len(result) > 1

    def test_overlap_exists(self):
        paras = [f"段落{i}的内容" for i in range(20)]
        text = "\n".join(paras)
        result = split_fixed(text, chunk_size=50, overlap=20)
        # 后一个 chunk 的开头应该和前一个 chunk 的结尾有重叠
        if len(result) >= 2:
            # overlap 部分应该同时出现在相邻的两个 chunk 中
            last_part_of_first = result[0].split("\n")[-1]
            assert last_part_of_first in result[1]

    def test_empty_text(self):
        result = split_fixed("", chunk_size=100)
        assert len(result) == 1


# ============================================================
# 父子 chunk 测试
# ============================================================


class TestMakeId:
    def test_deterministic(self):
        id1 = _make_id("a.pdf", "parent", 0, 0)
        id2 = _make_id("a.pdf", "parent", 0, 0)
        assert id1 == id2

    def test_different_inputs(self):
        id1 = _make_id("a.pdf", "parent", 0, 0)
        id2 = _make_id("a.pdf", "child", 0, 0)
        assert id1 != id2


class TestSplitIntoSubSections:
    def test_short_text_no_split(self):
        result = _split_into_sub_sections("短文本", max_size=300)
        assert len(result) == 1

    def test_splits_by_sub_items(self):
        text = "标题\n\n（一）第一项内容很长" + "x" * 200 + "\n\n（二）第二项内容" + "y" * 200
        result = _split_into_sub_sections(text, max_size=300)
        assert len(result) >= 2

    def test_fallback_to_fixed(self):
        """无子项结构时，用固定长度切割"""
        text = "\n".join(f"第{i}段没有子项结构的长文本内容。" for i in range(50))
        result = _split_into_sub_sections(text, max_size=200)
        assert len(result) > 1


class TestCreateParentChildChunks:
    def test_basic_structure(self):
        md = "# 标题\n\n#### 一、第一节\n\n内容1\n\n#### 二、第二节\n\n内容2"
        metadata = {"source": "test.txt", "title": "测试"}

        parents, children = create_parent_child_chunks(md, metadata)

        assert len(parents) >= 2
        assert len(children) >= 2

        # 检查父 chunk 结构
        for p in parents:
            assert "id" in p
            assert "text" in p
            assert p["metadata"]["role"] == "parent"
            assert p["metadata"]["source"] == "test.txt"

        # 检查子 chunk 结构
        for c in children:
            assert c["metadata"]["role"] == "child"
            assert "parent_id" in c["metadata"]
            # parent_id 应指向真实存在的父 chunk
            parent_ids = {p["id"] for p in parents}
            assert c["metadata"]["parent_id"] in parent_ids

    def test_child_inherits_metadata(self):
        md = "# 标题\n\n#### 一、节\n\n内容"
        metadata = {"source": "x.pdf", "title": "T", "category": "融资支持"}

        parents, children = create_parent_child_chunks(md, metadata)

        for c in children:
            assert c["metadata"]["source"] == "x.pdf"
            assert c["metadata"]["category"] == "融资支持"

    def test_ids_are_unique(self):
        md = "# 标题\n\n#### 一、A\n\n内容1\n\n#### 二、B\n\n内容2"
        parents, children = create_parent_child_chunks(md, {"source": "t.pdf"})

        all_ids = [p["id"] for p in parents] + [c["id"] for c in children]
        assert len(all_ids) == len(set(all_ids))

    def test_none_metadata_skipped(self):
        md = "# 标题\n\n内容"
        metadata = {"source": "t.pdf", "title": None, "policy_number": None}

        parents, children = create_parent_child_chunks(md, metadata)

        for p in parents:
            assert "title" not in p["metadata"]
            assert "policy_number" not in p["metadata"]


class TestChunkingOnRealData:
    @pytest.mark.skipif(
        not os.path.exists("data/parsed/优质中小企业梯度培育管理办法(1).md"),
        reason="测试数据不存在",
    )
    def test_management_regulation(self):
        """章+条结构文档"""
        with open("data/parsed/优质中小企业梯度培育管理办法(1).md") as f:
            md = f.read()

        parents, children = create_parent_child_chunks(
            md, {"source": "管理办法.pdf"}, parent_max_size=1000, child_max_size=300,
        )

        assert len(parents) > 10  # 应该有30+个条
        assert len(children) >= len(parents)  # 子 chunk 不少于父 chunk
        # 所有子 chunk 都应该有 parent_id
        parent_ids = {p["id"] for p in parents}
        for c in children:
            assert c["metadata"]["parent_id"] in parent_ids

    @pytest.mark.skipif(
        not os.path.exists("data/parsed/关于实施中小微企业贷款贴息政策的通知.md"),
        reason="测试数据不存在",
    )
    def test_policy_notice(self):
        """节结构文档"""
        with open("data/parsed/关于实施中小微企业贷款贴息政策的通知.md") as f:
            md = f.read()

        parents, children = create_parent_child_chunks(
            md, {"source": "贴息通知.txt"}, parent_max_size=1000, child_max_size=300,
        )

        assert len(parents) >= 3  # 至少3个大节
        assert len(children) > len(parents)  # 每节应有多个子 chunk
