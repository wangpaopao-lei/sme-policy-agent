"""固定长度分块（兜底策略）

当语义分块产生的 section 超过最大长度时，用固定长度切割。
按段落边界切割，保留 overlap。
"""


def split_fixed(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """
    按段落边界固定长度切割。

    参数:
        text: 待切割文本
        chunk_size: 每个 chunk 的目标大小（字符数）
        overlap: chunk 间重叠字符数

    返回: chunk 文本列表
    """
    if len(text) <= chunk_size:
        return [text]

    paragraphs = text.split("\n")
    chunks = []
    current_parts = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para) + 1  # +1 for newline

        if current_len + para_len > chunk_size and current_parts:
            # 当前 chunk 已满，保存
            chunk_text = "\n".join(current_parts)
            chunks.append(chunk_text)

            # 构建 overlap：从后往前取段落直到达到 overlap 长度
            overlap_parts = []
            overlap_len = 0
            for p in reversed(current_parts):
                if overlap_len + len(p) > overlap:
                    break
                overlap_parts.insert(0, p)
                overlap_len += len(p) + 1

            current_parts = overlap_parts + [para]
            current_len = sum(len(p) + 1 for p in current_parts)
        else:
            current_parts.append(para)
            current_len += para_len

    # 最后一个 chunk
    if current_parts:
        chunk_text = "\n".join(current_parts)
        if chunk_text.strip():
            chunks.append(chunk_text)

    return chunks if chunks else [text]
