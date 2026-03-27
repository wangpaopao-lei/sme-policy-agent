import os
from pathlib import Path

from bs4 import BeautifulSoup
import pdfplumber


def load_html(file_path: str) -> dict:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()

    soup = BeautifulSoup(html, "lxml")

    # 提取标题
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    elif soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    # 移除无用标签
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = "\n".join(lines)

    return {
        "text": text,
        "source": Path(file_path).name,
        "title": title or Path(file_path).stem,
        "file_type": "html",
    }


def load_pdf(file_path: str) -> dict:
    pages_text = []
    title = ""

    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text()
            if page_text:
                pages_text.append(page_text)
            # 用第一页第一行作为标题
            if i == 0 and page_text:
                first_line = page_text.strip().splitlines()[0]
                title = first_line.strip()

    text = "\n".join(pages_text)

    return {
        "text": text,
        "source": Path(file_path).name,
        "title": title or Path(file_path).stem,
        "file_type": "pdf",
    }


def load_txt(file_path: str) -> dict:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    # 用第一行非空内容作为标题
    title = lines[0] if lines else Path(file_path).stem
    text = "\n".join(lines)

    return {
        "text": text,
        "source": Path(file_path).name,
        "title": title or Path(file_path).stem,
        "file_type": "txt",
    }


def load_file(file_path: str) -> dict:
    ext = Path(file_path).suffix.lower()
    if ext == ".html":
        return load_html(file_path)
    elif ext == ".pdf":
        return load_pdf(file_path)
    elif ext == ".txt":
        return load_txt(file_path)
    else:
        raise ValueError(f"不支持的文件类型: {ext}")


def load_all(data_dir: str) -> list[dict]:
    docs = []
    data_path = Path(data_dir)

    files = (sorted(data_path.glob("**/*.html"))
             + sorted(data_path.glob("**/*.pdf"))
             + sorted(data_path.glob("**/*.txt")))

    for file_path in files:
        try:
            doc = load_file(str(file_path))
            if doc["text"].strip():
                docs.append(doc)
                print(f"  [OK] {doc['source']} ({doc['file_type']}, {len(doc['text'])} 字)")
            else:
                print(f"  [SKIP] {file_path.name}（内容为空）")
        except Exception as e:
            print(f"  [ERROR] {file_path.name}: {e}")

    return docs
