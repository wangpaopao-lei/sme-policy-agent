import sys
import os
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingestion.loader import load_html, load_txt, load_file, load_all


# ── 测试 HTML 加载 ────────────────────────────────────────────────────────────

def test_load_html_extracts_text(tmp_path):
    html_file = tmp_path / "test.html"
    html_file.write_text("""
        <html>
          <head><title>政策标题</title></head>
          <body><p>这是政策正文内容。</p></body>
        </html>
    """, encoding="utf-8")

    doc = load_html(str(html_file))

    assert "政策正文内容" in doc["text"]
    assert doc["title"] == "政策标题"
    assert doc["source"] == "test.html"
    assert doc["file_type"] == "html"


def test_load_html_removes_script_and_style(tmp_path):
    html_file = tmp_path / "test.html"
    html_file.write_text("""
        <html><body>
          <script>var x = 1;</script>
          <style>.foo { color: red; }</style>
          <p>有效内容</p>
        </body></html>
    """, encoding="utf-8")

    doc = load_html(str(html_file))

    assert "var x" not in doc["text"]
    assert ".foo" not in doc["text"]
    assert "有效内容" in doc["text"]


def test_load_html_falls_back_to_h1_title(tmp_path):
    html_file = tmp_path / "test.html"
    html_file.write_text("""
        <html><body>
          <h1>一级标题</h1>
          <p>内容</p>
        </body></html>
    """, encoding="utf-8")

    doc = load_html(str(html_file))
    assert doc["title"] == "一级标题"


def test_load_html_falls_back_to_filename_when_no_title(tmp_path):
    html_file = tmp_path / "my_policy.html"
    html_file.write_text("<html><body><p>内容</p></body></html>", encoding="utf-8")

    doc = load_html(str(html_file))
    assert doc["title"] == "my_policy"


# ── 测试 load_txt ─────────────────────────────────────────────────────────────

def test_load_txt_extracts_text(tmp_path):
    txt_file = tmp_path / "policy.txt"
    txt_file.write_text("关于贷款贴息政策的通知\n\n一、政策目标\n支持中小企业发展。", encoding="utf-8")

    doc = load_txt(str(txt_file))
    assert "支持中小企业发展" in doc["text"]
    assert doc["title"] == "关于贷款贴息政策的通知"
    assert doc["source"] == "policy.txt"
    assert doc["file_type"] == "txt"


def test_load_txt_uses_first_line_as_title(tmp_path):
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("第一行是标题\n第二行是内容", encoding="utf-8")
    doc = load_txt(str(txt_file))
    assert doc["title"] == "第一行是标题"


# ── 测试 load_file 路由 ───────────────────────────────────────────────────────

def test_load_file_routes_txt(tmp_path):
    txt_file = tmp_path / "policy.txt"
    txt_file.write_text("政策标题\n政策内容", encoding="utf-8")
    doc = load_file(str(txt_file))
    assert doc["file_type"] == "txt"


def test_load_file_unsupported_extension(tmp_path):
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("some,data")

    with pytest.raises(ValueError, match="不支持的文件类型"):
        load_file(str(csv_file))


# ── 测试 load_all ─────────────────────────────────────────────────────────────

def test_load_all_returns_only_nonempty_docs(tmp_path):
    # 一个有内容的 HTML
    (tmp_path / "a.html").write_text(
        "<html><body><p>政策内容A</p></body></html>", encoding="utf-8"
    )
    # 一个空 HTML（只有标签，无文字）
    (tmp_path / "empty.html").write_text(
        "<html><body></body></html>", encoding="utf-8"
    )

    docs = load_all(str(tmp_path))

    sources = [d["source"] for d in docs]
    assert "a.html" in sources
    assert "empty.html" not in sources


def test_load_all_scans_subdirectories(tmp_path):
    subdir = tmp_path / "sub"
    subdir.mkdir()
    (subdir / "b.html").write_text(
        "<html><body><p>子目录文件</p></body></html>", encoding="utf-8"
    )

    docs = load_all(str(tmp_path))
    assert any(d["source"] == "b.html" for d in docs)


def test_load_all_returns_correct_file_types(tmp_path):
    (tmp_path / "policy.html").write_text(
        "<html><body><p>HTML文件内容</p></body></html>", encoding="utf-8"
    )

    docs = load_all(str(tmp_path))
    assert all(d["file_type"] in ("html", "pdf") for d in docs)


# ── 集成测试：用真实数据文件 ──────────────────────────────────────────────────

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

@pytest.mark.skipif(not os.path.exists(DATA_DIR), reason="data/ 目录不存在")
def test_load_all_real_data():
    docs = load_all(DATA_DIR)
    assert len(docs) > 0, "应至少加载到一篇文档"
    for doc in docs:
        assert doc["text"].strip(), f"{doc['source']} 的 text 不应为空"
        assert doc["source"], "source 不应为空"
        assert doc["title"], "title 不应为空"
        assert doc["file_type"] in ("html", "pdf")
