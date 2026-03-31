"""BM25 关键词检索索引

基于 rank_bm25 + jieba 分词，支持：
  - 从 chunk 文本构建索引
  - 加权关键词索引（用于表格 Q&K）
  - 持久化（pickle 序列化）
"""

import os
import pickle
import re

import jieba
from rank_bm25 import BM25Okapi


# 政策领域自定义词典（提升分词准确度）
CUSTOM_WORDS = [
    "中小微企业", "中小企业", "专精特新", "小巨人",
    "贷款贴息", "融资担保", "融资租赁", "政府性融资担保",
    "设备更新", "技术改造", "产业升级",
    "工业互联网", "人工智能", "新质生产力", "新型工业化",
    "跨境电商", "跨境电子商务",
    "企业年金", "社保", "养老保险",
    "固体废物", "循环利用",
    "科技创新", "知识产权",
    "增值税", "消费税", "所得税", "进口关税",
    "工信部", "财政部", "科技部", "发改委",
    "国务院", "海关总署", "税务总局", "金融监管总局",
]

# 初始化 jieba 自定义词典
for word in CUSTOM_WORDS:
    jieba.add_word(word)


def _tokenize(text: str) -> list[str]:
    """jieba 分词 + 过滤停用词和短词"""
    # 去除 Markdown 格式标记
    text = re.sub(r'[#*>\-|`]', ' ', text)
    text = re.sub(r'\s+', ' ', text)

    tokens = jieba.lcut(text)

    # 过滤：去掉单字符、纯数字、纯标点
    filtered = [
        t for t in tokens
        if len(t) >= 2
        and not t.isspace()
        and not re.match(r'^[\d.%]+$', t)
        and not re.match(r'^[，。、；：\u201c\u201d\u2018\u2019（）《》【】\s]+$', t)
    ]

    return filtered


class BM25Store:
    """BM25 关键词检索索引"""

    def __init__(self):
        self._chunks: list[dict] = []      # [{id, text, source, ...}]
        self._tokenized: list[list[str]] = []
        self._bm25: BM25Okapi | None = None

    def build_index(self, chunks: list[dict]) -> None:
        """
        从 chunk 列表构建 BM25 索引。

        参数:
            chunks: [{id, text, metadata}]，每个 chunk 需要有 id 和 text
        """
        self._chunks = chunks
        self._tokenized = [_tokenize(c["text"]) for c in chunks]

        if self._tokenized:
            self._bm25 = BM25Okapi(self._tokenized)
        else:
            self._bm25 = None

    def add_weighted_keywords(self, chunk_id: str, keywords: dict[str, int]) -> None:
        """
        为指定 chunk 添加加权关键词（表格 Q&K 用）。
        通过重复关键词实现权重效果。

        参数:
            chunk_id: chunk 的 ID
            keywords: {"关键词": 权重} 如 {"贷款贴息": 5, "小型企业": 3}
        """
        # 找到对应 chunk 的索引
        idx = None
        for i, c in enumerate(self._chunks):
            if c["id"] == chunk_id:
                idx = i
                break

        if idx is None:
            return

        # 将加权关键词添加到分词结果中（重复 N 次 = 权重 N）
        extra_tokens = []
        for word, weight in keywords.items():
            extra_tokens.extend([word] * weight)

        self._tokenized[idx].extend(extra_tokens)

        # 重建索引
        if self._tokenized:
            self._bm25 = BM25Okapi(self._tokenized)

    def search(self, query: str, top_k: int = 20) -> list[dict]:
        """
        BM25 检索。

        返回: [{id, text, score, metadata}]，按分数降序
        """
        if not self._bm25 or not self._chunks:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)

        # 按分数排序，取 top_k
        scored_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )[:top_k]

        results = []
        for idx in scored_indices:
            if scores[idx] > 0:
                chunk = self._chunks[idx]
                results.append({
                    "id": chunk["id"],
                    "text": chunk["text"],
                    "score": float(scores[idx]),
                    "metadata": chunk.get("metadata", {}),
                })

        return results

    def count(self) -> int:
        return len(self._chunks)

    def save(self, path: str) -> None:
        """持久化索引到文件"""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        data = {
            "chunks": self._chunks,
            "tokenized": self._tokenized,
        }
        with open(path, "wb") as f:
            pickle.dump(data, f)

    def load(self, path: str) -> None:
        """从文件加载索引"""
        with open(path, "rb") as f:
            data = pickle.load(f)

        self._chunks = data["chunks"]
        self._tokenized = data["tokenized"]
        if self._tokenized:
            self._bm25 = BM25Okapi(self._tokenized)
        else:
            self._bm25 = None
