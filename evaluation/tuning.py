"""参数调优实验框架

支持对 chunk 大小、RRF k 值、检索 top_k 等参数进行对比实验。
每次实验记录参数配置和评估结果，输出对比报告。

用法：
    python evaluation/tuning.py --param rrf_k --values 20,40,60,80,100
    python evaluation/tuning.py --param top_k --values 3,5,7,10
    python evaluation/tuning.py --param threshold --values 0.85,0.90,0.92,0.95
"""

import sys
import os
import json
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_eval_set(path: str = "evaluation/dataset/eval_set.json") -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_retrieval_experiment(
    eval_set: list[dict],
    embedder,
    store,
    bm25_store,
    rrf_k: int = 60,
    top_k: int = 5,
    reranker=None,
    use_rerank: bool = True,
) -> dict:
    """
    运行单次检索实验。

    返回: {params, recall_at_k, mrr, by_category, failures}
    """
    from src.retrieval.hybrid_searcher import HybridSearcher, rrf_merge
    from evaluation.retrieval_eval import recall_at_k, mrr, evaluate_retrieval

    searcher = HybridSearcher(
        vector_store=store,
        bm25_store=bm25_store,
        embedder=embedder,
        reranker=reranker,
    )

    results = []
    for item in eval_set:
        if not item["expected_sources"]:
            continue

        chunks = searcher.search(
            query=item["question"],
            top_k=top_k,
            use_rerank=use_rerank,
            expand_parents=False,
        )

        retrieved_sources = []
        for c in chunks:
            meta = c.get("metadata", {})
            source = meta.get("source", c.get("source", ""))
            if source and source not in retrieved_sources:
                retrieved_sources.append(source)

        results.append({
            "question": item["question"],
            "expected_sources": item["expected_sources"],
            "retrieved_sources": retrieved_sources,
            "category": item["category"],
        })

    report = evaluate_retrieval(results, k=top_k)
    return report


def run_param_sweep(
    param_name: str,
    param_values: list,
    eval_set: list[dict],
    embedder,
    store,
    bm25_store,
    reranker=None,
    base_params: dict | None = None,
) -> list[dict]:
    """
    对单个参数进行扫描实验。

    参数:
        param_name: 参数名（rrf_k, top_k, threshold）
        param_values: 参数值列表
        base_params: 其他参数的基准值

    返回: [{value, recall_at_k, mrr, time_sec}]
    """
    base = base_params or {"rrf_k": 60, "top_k": 7, "use_rerank": True}

    results = []
    for value in param_values:
        params = {**base, param_name: value}
        print(f"  测试 {param_name}={value} ...")

        start = time.time()
        report = run_retrieval_experiment(
            eval_set=eval_set,
            embedder=embedder,
            store=store,
            bm25_store=bm25_store,
            rrf_k=params.get("rrf_k", 60),
            top_k=params.get("top_k", 5),
            reranker=reranker,
            use_rerank=params.get("use_rerank", True),
        )
        elapsed = round(time.time() - start, 2)

        results.append({
            "value": value,
            "recall_at_k": report["overall"]["recall_at_k"],
            "mrr": report["overall"]["mrr"],
            "time_sec": elapsed,
            "failures": len(report.get("failures", [])),
        })

        print(f"    Recall@K={results[-1]['recall_at_k']:.4f}  "
              f"MRR={results[-1]['mrr']:.4f}  "
              f"耗时={elapsed}s  "
              f"失败={results[-1]['failures']}")

    return results


def save_experiment(
    param_name: str,
    results: list[dict],
    output_dir: str = "evaluation/reports",
) -> str:
    """保存实验结果"""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"tuning_{param_name}_{timestamp}.json"
    path = os.path.join(output_dir, filename)

    report = {
        "param_name": param_name,
        "timestamp": timestamp,
        "results": results,
        "best": max(results, key=lambda r: r["recall_at_k"]),
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return path


def print_comparison_table(param_name: str, results: list[dict]) -> None:
    """打印对比表格"""
    print(f"\n{'=' * 60}")
    print(f"参数调优结果: {param_name}")
    print(f"{'=' * 60}")
    print(f"{'值':>10} | {'Recall@K':>10} | {'MRR':>10} | {'耗时(s)':>10} | {'失败':>6}")
    print("-" * 60)
    for r in results:
        marker = " ★" if r == max(results, key=lambda x: x["recall_at_k"]) else ""
        print(f"{str(r['value']):>10} | {r['recall_at_k']:>10.4f} | {r['mrr']:>10.4f} | {r['time_sec']:>10.2f} | {r['failures']:>6}{marker}")
    print(f"{'=' * 60}")

    best = max(results, key=lambda r: r["recall_at_k"])
    print(f"\n最优值: {param_name}={best['value']} (Recall={best['recall_at_k']:.4f}, MRR={best['mrr']:.4f})")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="参数调优实验")
    parser.add_argument("--param", required=True, help="参数名: rrf_k, top_k, use_rerank")
    parser.add_argument("--values", required=True, help="逗号分隔的参数值列表")
    args = parser.parse_args()

    # 解析参数值
    values_str = args.values.split(",")
    if args.param in ("rrf_k", "top_k"):
        values = [int(v) for v in values_str]
    elif args.param == "use_rerank":
        values = [v.lower() == "true" for v in values_str]
    else:
        values = [float(v) for v in values_str]

    # 加载依赖（重型依赖）
    import config
    from src.retrieval.embedder import Embedder
    from src.retrieval.vector_store import VectorStore
    from src.retrieval.bm25_store import BM25Store

    print("加载模型和索引...")
    embedder = Embedder(model_name=config.EMBEDDING_MODEL)
    store = VectorStore(
        chroma_path=config.CHROMA_PATH,
        collection_name=config.CHROMA_COLLECTION + "_v2",
    )
    bm25 = BM25Store()
    bm25_path = os.path.join(config.CHROMA_PATH, "bm25_index.pkl")
    if os.path.exists(bm25_path):
        bm25.load(bm25_path)

    # 加载 Reranker（use_rerank 实验需要）
    reranker = None
    if args.param == "use_rerank":
        print("加载 Reranker 模型...")
        from src.retrieval.reranker import Reranker
        reranker = Reranker()

    eval_set = load_eval_set()
    print(f"评估集: {len(eval_set)} 条\n")

    results = run_param_sweep(
        param_name=args.param,
        param_values=values,
        eval_set=eval_set,
        embedder=embedder,
        store=store,
        bm25_store=bm25,
        reranker=reranker,
    )

    print_comparison_table(args.param, results)
    path = save_experiment(args.param, results)
    print(f"\n结果已保存: {path}")
