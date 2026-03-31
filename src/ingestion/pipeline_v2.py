"""文档处理流水线 v2

串联完整的文档处理流程：
  扫描文件 → 解析 → 元数据提取 → 表格处理 → 清洗 → 输出标准化 Markdown

旧的 pipeline.py（v1）负责 load → chunk → embed → store，本模块只负责
文档解析和标准化，chunk/embed/store 将在 Phase 2 中升级。
"""

import os
from pathlib import Path

import anthropic

import config
from src.ingestion.parsers.pdf_parser import parse_pdf
from src.ingestion.parsers.html_parser import parse_html
from src.ingestion.parsers.md_parser import parse_markdown
from src.ingestion.metadata.regex_extractor import extract_metadata_by_regex, get_missing_fields
from src.ingestion.metadata.llm_extractor import extract_metadata_by_llm
from src.ingestion.table.table_processor import process_tables
from src.ingestion.cleaner import build_final_document


# 文件扩展名 → 解析器映射
PARSER_MAP = {
    ".pdf": parse_pdf,
    ".html": parse_html,
    ".htm": parse_html,
    ".md": parse_markdown,
    ".txt": parse_markdown,  # TXT 文件按 Markdown 格式处理
}


def _merge_metadata(
    parser_meta: dict,
    regex_meta: dict,
    llm_meta: dict,
    source: str,
    file_type: str,
) -> dict:
    """
    合并多来源的元数据，优先级：parser_meta > regex_meta > llm_meta。
    确保 source 和 file_type 始终存在。
    """
    merged = {
        "source": source,
        "file_type": file_type,
    }

    all_fields = [
        "title", "policy_number", "issuing_authority",
        "publish_date", "effective_date", "expiry_date",
        "applicable_region", "category",
    ]

    for field in all_fields:
        # 按优先级取值
        value = (
            parser_meta.get(field)
            or regex_meta.get(field)
            or llm_meta.get(field)
        )
        if value is not None:
            merged[field] = value

    return merged


def process_file(
    file_path: str,
    use_llm: bool = True,
    client: anthropic.Anthropic | None = None,
) -> dict | None:
    """
    处理单个文件：解析 → 元数据 → 表格处理 → 清洗。

    参数:
        file_path: 文件路径
        use_llm: 是否使用 LLM 兜底（元数据提取 + 表格 Q&K）
        client: Anthropic 客户端（可选）

    返回:
    {
        "final_document": str,       # 带 frontmatter 的标准化 Markdown
        "metadata": dict,            # 合并后的完整元数据
        "tables": list[dict],        # 处理后的表格（含 Q&K）
        "source": str,               # 文件名
    }
    出错返回 None。
    """
    ext = Path(file_path).suffix.lower()
    parser = PARSER_MAP.get(ext)
    if parser is None:
        print(f"  [SKIP] {Path(file_path).name}（不支持的格式: {ext}）")
        return None

    # 1. 解析文件
    try:
        parsed = parser(file_path)
    except Exception as e:
        print(f"  [ERROR] {Path(file_path).name} 解析失败: {e}")
        return None

    if not parsed["markdown"].strip():
        print(f"  [SKIP] {Path(file_path).name}（内容为空）")
        return None

    # 2. 元数据提取
    # 2a. parser 自带的元数据
    parser_meta = {}
    if "title" in parsed:
        parser_meta["title"] = parsed["title"]
    if "meta_tags" in parsed:
        # HTML meta 标签中可能有 publish_source
        pub_source = parsed["meta_tags"].get("publish_source")
        if pub_source:
            parser_meta["issuing_authority"] = pub_source

    # 2b. 正则提取
    regex_meta = extract_metadata_by_regex(parsed["raw_text"])

    # 2c. LLM 兜底
    llm_meta = {}
    if use_llm and client is not None:
        missing = get_missing_fields(regex_meta)
        # 排除不太重要的字段，减少 LLM 调用
        important_missing = [
            f for f in missing
            if f in ("title", "policy_number", "issuing_authority", "publish_date", "category")
        ]
        if important_missing:
            try:
                llm_meta = extract_metadata_by_llm(
                    text=parsed["raw_text"],
                    missing_fields=important_missing,
                    client=client,
                )
            except Exception as e:
                print(f"  [WARN] {parsed['source']} LLM 元数据提取失败: {e}")

    # 合并元数据
    metadata = _merge_metadata(
        parser_meta=parser_meta,
        regex_meta=regex_meta,
        llm_meta=llm_meta,
        source=parsed["source"],
        file_type=parsed["file_type"],
    )

    # 3. 表格处理
    processed_tables = []
    if parsed["tables"]:
        if use_llm and client is not None:
            try:
                processed_tables = process_tables(
                    tables=parsed["tables"],
                    title=metadata.get("title", ""),
                    full_markdown=parsed["markdown"],
                    client=client,
                )
            except Exception as e:
                print(f"  [WARN] {parsed['source']} 表格处理失败: {e}")
                processed_tables = parsed["tables"]
        else:
            # 不用 LLM 时保留原始表格
            processed_tables = parsed["tables"]

    # 4. 清洗 + 生成最终文档
    final_document = build_final_document(parsed["markdown"], metadata)

    return {
        "final_document": final_document,
        "metadata": metadata,
        "tables": processed_tables,
        "source": parsed["source"],
    }


def run_pipeline(
    data_dir: str = "data",
    output_dir: str = "data/parsed",
    use_llm: bool = True,
) -> dict:
    """
    完整摄入流水线：扫描 → 解析 → 元数据 → 表格处理 → 输出。

    参数:
        data_dir: 原始文件目录
        output_dir: 输出目录
        use_llm: 是否使用 LLM（关闭则跳过 LLM 兜底和表格 Q&K）

    返回:
    {
        "total_files": int,
        "processed": int,
        "failed": list[str],
        "documents": list[dict],
    }
    """
    data_path = Path(data_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 扫描所有支持的文件
    files = []
    for ext in PARSER_MAP:
        files.extend(sorted(data_path.glob(f"**/*{ext}")))

    # 去重（同一文件可能被多个 glob 匹配到）
    files = sorted(set(files))

    print(f"=== 文档处理流水线 v2 ===")
    print(f"扫描目录: {data_dir}")
    print(f"输出目录: {output_dir}")
    print(f"LLM 兜底: {'开启' if use_llm else '关闭'}")
    print(f"找到 {len(files)} 个文件\n")

    # 初始化 LLM 客户端
    client = None
    if use_llm and config.ANTHROPIC_API_KEY:
        try:
            client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        except Exception:
            print("[WARN] 无法初始化 Anthropic 客户端，LLM 兜底已关闭")
            use_llm = False

    documents = []
    failed = []

    for file_path in files:
        print(f"处理: {file_path.name}")
        result = process_file(
            file_path=str(file_path),
            use_llm=use_llm,
            client=client,
        )

        if result is None:
            failed.append(file_path.name)
            continue

        # 写入输出文件
        out_name = Path(result["source"]).stem + ".md"
        out_path = output_path / out_name
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(result["final_document"])

        documents.append(result)
        table_info = f"，{len(result['tables'])} 个表格" if result["tables"] else ""
        print(f"  [OK] → {out_name} ({result['metadata'].get('category', '未分类')}{table_info})")

    print(f"\n=== 处理完成 ===")
    print(f"成功: {len(documents)}/{len(files)}，失败: {len(failed)}")
    if failed:
        print(f"失败文件: {failed}")

    return {
        "total_files": len(files),
        "processed": len(documents),
        "failed": failed,
        "documents": documents,
    }
