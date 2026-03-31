"""一键评估脚本

用法：
  python evaluation/run_eval.py                     # 只跑检索评估（快速，不需要 LLM）
  python evaluation/run_eval.py --full               # 完整评估（检索+RAGAS+LLM-as-Judge）
  python evaluation/run_eval.py --judge              # 检索+LLM-as-Judge（不跑 RAGAS）
"""

import argparse
import json
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.retrieval_eval import evaluate_retrieval
from evaluation.answer_eval import run_ragas_evaluation, run_judge_evaluation


def load_eval_set(path: str = "evaluation/dataset/eval_set.json") -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_retrieval_only(eval_set: list[dict], agent) -> dict:
    """只运行检索评估（不调 LLM 生成回答）"""
    eval_results = []

    for item in eval_set:
        # 通过 agent 的检索工具获取检索结果
        # 简化版：直接调用底层检索
        try:
            from src.retrieval.embedder import Embedder
            from src.retrieval.store import PolicyStore
            import config

            embedder = Embedder(model_name=config.EMBEDDING_MODEL)
            store = PolicyStore(
                chroma_path=config.CHROMA_PATH,
                collection_name=config.CHROMA_COLLECTION,
            )

            embedding = embedder.embed(item["question"])
            results = store.query(embedding, top_k=5)
            retrieved_sources = [r["source"] for r in results]
        except Exception as e:
            print(f"  [ERROR] 检索失败: {e}")
            retrieved_sources = []

        eval_results.append({
            "question": item["question"],
            "expected_sources": item["expected_sources"],
            "retrieved_sources": retrieved_sources,
            "category": item["category"],
        })

    return evaluate_retrieval(eval_results, k=5)


def run_full_evaluation(eval_set: list[dict], agent) -> dict:
    """完整评估：检索 + Agent回答 + RAGAS + LLM-as-Judge"""
    retrieval_results = []
    answer_eval_data = []

    print("=== 生成回答 ===")
    for i, item in enumerate(eval_set):
        print(f"  [{i+1}/{len(eval_set)}] {item['question'][:30]}...")
        try:
            result = agent.chat(item["question"])
            answer = result["answer"]
            sources = result["sources"]
        except Exception as e:
            print(f"    [ERROR] {e}")
            answer = ""
            sources = []

        retrieval_results.append({
            "question": item["question"],
            "expected_sources": item["expected_sources"],
            "retrieved_sources": sources,
            "category": item["category"],
        })

        answer_eval_data.append({
            "question": item["question"],
            "answer": answer,
            "contexts": [],  # TODO: 从 Agent 中获取实际 contexts
            "ground_truth": item["expected_answer"],
            "category": item["category"],
        })

    # 检索评估
    print("\n=== 检索评估 ===")
    retrieval_report = evaluate_retrieval(retrieval_results, k=5)

    # RAGAS 评估
    print("\n=== RAGAS 评估 ===")
    ragas_report = run_ragas_evaluation(answer_eval_data)

    # LLM-as-Judge 评估
    print("\n=== LLM-as-Judge 评估 ===")
    judge_report = run_judge_evaluation(answer_eval_data)

    return {
        "retrieval": retrieval_report,
        "ragas": ragas_report,
        "judge": judge_report,
    }


def print_report(report: dict, mode: str = "retrieval"):
    """打印评估报告"""
    print("\n" + "=" * 60)
    print(f"  评估报告 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    print("=" * 60)

    if "retrieval" in report:
        r = report["retrieval"]
        print(f"\n--- 检索指标 ---")
        print(f"  Recall@5: {r['overall']['recall_at_k']:.3f}")
        print(f"  MRR:      {r['overall']['mrr']:.3f}")
        print(f"  总计:     {r['overall']['total']} 条")

        if r["by_category"]:
            print(f"\n  按类别:")
            for cat, scores in sorted(r["by_category"].items()):
                print(f"    {cat}: Recall={scores['recall_at_k']:.3f} MRR={scores['mrr']:.3f} ({scores['total']}条)")

        if r["failures"]:
            print(f"\n  失败案例 ({len(r['failures'])} 条):")
            for fail in r["failures"][:5]:
                print(f"    Q: {fail['question'][:40]}")
                print(f"    期望: {fail['expected']}")
                print(f"    实际: {fail['retrieved']}")

    if report.get("ragas"):
        print(f"\n--- RAGAS 指标 ---")
        for k, v in report["ragas"].items():
            if isinstance(v, float):
                print(f"  {k}: {v:.3f}")

    if report.get("judge"):
        j = report["judge"]
        print(f"\n--- LLM-as-Judge 指标（满分5） ---")
        for dim, score in j["overall"].items():
            print(f"  {dim}: {score:.2f}")

    print("\n" + "=" * 60)


def save_report(report: dict, path: str):
    """保存评估报告到 JSON"""

    def _serialize(obj):
        if isinstance(obj, float):
            return round(obj, 4)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=_serialize)
    print(f"\n报告已保存至: {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAG 系统评估")
    parser.add_argument("--full", action="store_true", help="完整评估")
    parser.add_argument("--judge", action="store_true", help="包含 LLM-as-Judge")
    parser.add_argument("--output", type=str, default=None, help="报告输出路径")
    args = parser.parse_args()

    eval_set = load_eval_set()
    print(f"加载评估数据集: {len(eval_set)} 条\n")

    if args.full or args.judge:
        # 需要初始化 Agent
        try:
            from src.agent.agent import PolicyAgent
            agent = PolicyAgent()
        except Exception as e:
            print(f"无法初始化 Agent: {e}")
            print("退回到纯检索评估模式")
            report = {"retrieval": run_retrieval_only(eval_set, None)}
            print_report(report)
            sys.exit(1)

        report = run_full_evaluation(eval_set, agent)
    else:
        report = {"retrieval": run_retrieval_only(eval_set, None)}

    print_report(report)

    output_path = args.output or f"evaluation/reports/eval_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    save_report(report, output_path)
