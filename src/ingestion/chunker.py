def chunk_document(doc: dict, chunk_size: int = 400, overlap: int = 50) -> list[dict]:
    text = doc["text"]
    source = doc["source"]
    title = doc["title"]

    # 先按段落切分
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    chunks = []
    current = ""
    chunk_index = 0

    for para in paragraphs:
        # 如果加入当前段落后超过 chunk_size，先保存当前块
        if current and len(current) + len(para) + 1 > chunk_size:
            chunks.append({
                "text": current.strip(),
                "source": source,
                "title": title,
                "chunk_index": chunk_index,
            })
            chunk_index += 1
            # 保留末尾 overlap 字符作为下一块的开头
            current = current[-overlap:] + "\n" + para if overlap > 0 else para
        else:
            current = current + "\n" + para if current else para

    # 保存最后一块
    if current.strip():
        chunks.append({
            "text": current.strip(),
            "source": source,
            "title": title,
            "chunk_index": chunk_index,
        })

    return chunks


def chunk_all(docs: list[dict], chunk_size: int = 400, overlap: int = 50) -> list[dict]:
    all_chunks = []
    for doc in docs:
        doc_chunks = chunk_document(doc, chunk_size, overlap)
        all_chunks.extend(doc_chunks)
    return all_chunks
