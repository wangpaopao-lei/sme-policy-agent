"""检索质量评估

基于评估数据集，计算 Recall@K 和 MRR 指标。
不依赖 LLM，可快速运行。
"""

import json


def _normalize_source(s: str) -> str:
    """归一化文件名中的引号和空格，避免全角/半角差异导致的匹配失败"""
    return (
        s.replace("\u201c", '"').replace("\u201d", '"')   # 中文双引号 "" → "
        .replace("\u2018", "'").replace("\u2019", "'")    # 中文单引号 '' → '
        .replace("\u300c", '"').replace("\u300d", '"')    # 日文引号 「」 → "
        .replace("\u3000", " ")                           # 全角空格
        .strip()
    )


def _source_match(retrieved: str, expected: str) -> bool:
    """比较两个 source 是否匹配（归一化后比较）"""
    return _normalize_source(retrieved) == _normalize_source(expected)


def recall_at_k(retrieved_sources: list[str], expected_sources: list[str], k: int = 5) -> float:
    """
    计算单个问题的 Recall@K。
    如果 expected_sources 中的任意一个出现在 top-k 结果中，则为 1。
    """
    if not expected_sources:
        return 1.0  # 无答案类问题，不需要检索

    top_k = retrieved_sources[:k]
    for expected in expected_sources:
        for retrieved in top_k:
            if _source_match(retrieved, expected):
                return 1.0
    return 0.0


def mrr(retrieved_sources: list[str], expected_sources: list[str]) -> float:
    """
    计算单个问题的 MRR (Mean Reciprocal Rank)。
    返回第一个正确结果的 1/rank。
    """
    if not expected_sources:
        return 1.0

    for rank, retrieved in enumerate(retrieved_sources, 1):
        for expected in expected_sources:
            if _source_match(retrieved, expected):
                return 1.0 / rank
    return 0.0


def evaluate_retrieval(eval_results: list[dict], k: int = 5) -> dict:
    """
    对一批评估结果计算检索指标。

    参数:
        eval_results: [{
            "question": str,
            "expected_sources": list[str],
            "retrieved_sources": list[str],
            "category": str,
        }]
        k: Recall@K 的 K 值

    返回:
    {
        "overall": {"recall_at_k": float, "mrr": float, "total": int},
        "by_category": {
            "简单事实": {"recall_at_k": float, "mrr": float, "total": int},
            ...
        },
        "failures": [{"question": str, "expected": list, "retrieved": list}]
    }
    """
    results_by_category = {}
    all_recalls = []
    all_mrrs = []
    failures = []

    for item in eval_results:
        r = recall_at_k(item["retrieved_sources"], item["expected_sources"], k)
        m = mrr(item["retrieved_sources"], item["expected_sources"])
        all_recalls.append(r)
        all_mrrs.append(m)

        cat = item.get("category", "其他")
        if cat not in results_by_category:
            results_by_category[cat] = {"recalls": [], "mrrs": []}
        results_by_category[cat]["recalls"].append(r)
        results_by_category[cat]["mrrs"].append(m)

        if r == 0.0 and item["expected_sources"]:
            failures.append({
                "question": item["question"],
                "expected": item["expected_sources"],
                "retrieved": item["retrieved_sources"][:k],
            })

    overall = {
        "recall_at_k": sum(all_recalls) / len(all_recalls) if all_recalls else 0,
        "mrr": sum(all_mrrs) / len(all_mrrs) if all_mrrs else 0,
        "total": len(eval_results),
    }

    by_category = {}
    for cat, data in results_by_category.items():
        by_category[cat] = {
            "recall_at_k": sum(data["recalls"]) / len(data["recalls"]),
            "mrr": sum(data["mrrs"]) / len(data["mrrs"]),
            "total": len(data["recalls"]),
        }

    return {
        "overall": overall,
        "by_category": by_category,
        "failures": failures,
    }
