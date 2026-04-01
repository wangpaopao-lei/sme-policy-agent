"""父子 chunk 生成

将文档分为两层：
  - 父 chunk（~1000字）：提供完整上下文，送给 Claude 阅读
  - 子 chunk（~300字）：用于检索命中，粒度细精度高

检索时用子 chunk 做向量匹配，命中后通过 parent_id 展开为父 chunk。
"""

import hashlib
import re

from src.chunking.structure_splitter import split_by_structure
from src.chunking.fixed_splitter import split_fixed


def _make_id(source: str, role: str, *parts) -> str:
    """生成确定性的 chunk ID"""
    raw = f"{source}::{role}::" + "::".join(str(p) for p in parts)
    return hashlib.md5(raw.encode()).hexdigest()


def _split_into_sub_sections(text: str, max_size: int = 300) -> list[str]:
    """
    将一个 section 进一步切分为子 chunk。

    优先按子结构切割（列表项、（一）（二）等），
    不够细则用固定长度兜底。
    """
    if len(text) <= max_size:
        return [text]

    # 尝试按子项切割：（一）（二）或 1. 2. 等
    sub_patterns = [
        r'(?=\n\s*[-•]\s*（[一二三四五六七八九十]+）)',    # - （一）
        r'(?=\n\s*（[一二三四五六七八九十]+）)',           # （一）
        r'(?=\n\s*[-•]\s*\d+[、.．])',                   # - 1、
        r'(?=\n\s*\d+[、.．]\s*\S)',                     # 1、
    ]

    for pattern in sub_patterns:
        parts = re.split(pattern, text)
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) >= 2 and all(len(p) <= max_size * 1.5 for p in parts):
            # 切割成功且每部分不会太大
            return parts

    # 子项切割无效，用固定长度兜底
    return split_fixed(text, chunk_size=max_size, overlap=50)


def create_parent_child_chunks(
    markdown: str,
    metadata: dict,
    parent_max_size: int = 1000,
    child_max_size: int = 300,
) -> tuple[list[dict], list[dict]]:
    """
    生成父子 chunk。

    参数:
        markdown: 文档 Markdown 内容（可含 frontmatter）
        metadata: 文档元数据
        parent_max_size: 父 chunk 最大字符数
        child_max_size: 子 chunk 最大字符数

    返回: (parent_chunks, child_chunks)

    parent_chunk:
    {
        "id": str,
        "text": str,
        "metadata": {
            ...文档元数据,
            "role": "parent",
            "section_path": str,
        }
    }

    child_chunk:
    {
        "id": str,
        "text": str,
        "metadata": {
            ...文档元数据,
            "role": "child",
            "parent_id": str,
            "section_path": str,
            "chunk_index": int,
        }
    }
    """
    source = metadata.get("source", "unknown")

    # 第一步：按标题结构切割为 sections（候选父 chunk）
    sections = split_by_structure(markdown, max_size=parent_max_size)

    parent_chunks = []
    child_chunks = []

    for p_idx, section in enumerate(sections):
        section_text = section["text"]
        section_heading = section.get("heading", "")

        # 父 chunk 超长时，用固定长度进一步切割
        if len(section_text) > parent_max_size * 1.5:
            parent_parts = split_fixed(section_text, chunk_size=parent_max_size, overlap=100)
        else:
            parent_parts = [section_text]

        for pp_idx, parent_text in enumerate(parent_parts):
            parent_id = _make_id(source, "parent", p_idx, pp_idx)

            parent_meta = {
                **{k: v for k, v in metadata.items() if v is not None},
                "role": "parent",
                "section_path": section_heading,
            }

            parent_chunks.append({
                "id": parent_id,
                "text": parent_text,
                "metadata": parent_meta,
            })

            # 第二步：父 chunk 内部切分为子 chunk
            sub_texts = _split_into_sub_sections(parent_text, max_size=child_max_size)

            for c_idx, child_text in enumerate(sub_texts):
                child_id = _make_id(source, "child", p_idx, pp_idx, c_idx)

                child_meta = {
                    **{k: v for k, v in metadata.items() if v is not None},
                    "role": "child",
                    "parent_id": parent_id,
                    "section_path": section_heading,
                    "chunk_index": c_idx,
                }

                child_chunks.append({
                    "id": child_id,
                    "text": child_text,
                    "metadata": child_meta,
                })

    return parent_chunks, child_chunks
