"""回答质量评估

支持两种评估方式：
1. RAGAS 框架评估（Context Precision/Recall, Faithfulness, Answer Relevancy）
2. 自建 LLM-as-Judge 评估（补充维度）
"""

import json

import anthropic

import config


# ============================================================
# RAGAS 评估
# ============================================================


def run_ragas_evaluation(eval_data: list[dict]) -> dict | None:
    """
    使用 RAGAS 框架评估 RAG 系统。

    参数:
        eval_data: [{
            "question": str,
            "answer": str,           # 系统生成的回答
            "contexts": list[str],   # 检索到的 chunk 文本列表
            "ground_truth": str,     # 标准答案
        }]

    返回: RAGAS 评估结果字典，或 None（RAGAS 不可用时）
    """
    try:
        from ragas import evaluate
        from ragas.metrics import (
            Faithfulness,
            ResponseRelevancy,
            LLMContextPrecisionWithoutReference,
            LLMContextRecall,
        )
        from ragas.llms import LangchainLLMWrapper
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from datasets import Dataset
    except ImportError:
        print("[WARN] RAGAS 或依赖未安装，跳过 RAGAS 评估")
        return None

    # 配置 LLM（使用 Claude）
    try:
        from langchain_openai import ChatOpenAI
        # RAGAS 通过 langchain 调用 LLM，这里配置 Anthropic 兼容接口
        # 如果没有 OpenAI key，使用 Anthropic 的 langchain 封装
    except ImportError:
        pass

    try:
        from langchain_community.chat_models import ChatAnthropic
        from langchain_community.embeddings import HuggingFaceEmbeddings

        llm = ChatAnthropic(
            model="claude-haiku-4-5-20251001",
            anthropic_api_key=config.ANTHROPIC_API_KEY,
        )
        embeddings = HuggingFaceEmbeddings(model_name=config.EMBEDDING_MODEL)

        ragas_llm = LangchainLLMWrapper(llm)
        ragas_embeddings = LangchainEmbeddingsWrapper(embeddings)
    except Exception as e:
        print(f"[WARN] 无法初始化 RAGAS LLM: {e}")
        return None

    # 构建 Dataset
    dataset_dict = {
        "question": [d["question"] for d in eval_data],
        "answer": [d["answer"] for d in eval_data],
        "contexts": [d["contexts"] for d in eval_data],
        "ground_truth": [d["ground_truth"] for d in eval_data],
    }
    dataset = Dataset.from_dict(dataset_dict)

    # 配置指标
    metrics = [
        LLMContextPrecisionWithoutReference(llm=ragas_llm),
        LLMContextRecall(llm=ragas_llm),
        Faithfulness(llm=ragas_llm),
        ResponseRelevancy(llm=ragas_llm, embeddings=ragas_embeddings),
    ]

    try:
        result = evaluate(dataset=dataset, metrics=metrics)
        return dict(result)
    except Exception as e:
        print(f"[ERROR] RAGAS 评估失败: {e}")
        return None


# ============================================================
# 自建 LLM-as-Judge 评估
# ============================================================

JUDGE_PROMPT = """请评估以下 RAG 系统的回答质量。

用户问题：{question}
检索到的上下文：{context}
系统回答：{answer}
参考答案：{expected_answer}

请从以下四个维度评分（1-5分），并说明理由：

1. 忠实度：回答是否完全基于检索到的上下文？有没有编造上下文中不存在的信息？
   5=完全忠实 1=严重编造

2. 相关性：回答是否直接回答了用户的问题？
   5=精准回答 1=完全跑题

3. 完整性：回答是否涵盖了上下文中所有相关信息？
   5=完全覆盖 1=严重遗漏

4. 正确性：回答与参考答案是否一致？
   5=完全一致 1=完全错误

只返回 JSON 格式：
{{"faithfulness": n, "relevance": n, "completeness": n, "correctness": n, "reason": "简要理由"}}"""


def judge_answer(
    question: str,
    answer: str,
    context: str,
    expected_answer: str,
    client: anthropic.Anthropic | None = None,
) -> dict:
    """
    用 Claude 评估单个回答的质量。

    返回:
    {
        "faithfulness": int (1-5),
        "relevance": int (1-5),
        "completeness": int (1-5),
        "correctness": int (1-5),
        "reason": str,
    }
    """
    if client is None:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    prompt = JUDGE_PROMPT.format(
        question=question,
        context=context[:2000],
        answer=answer,
        expected_answer=expected_answer,
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = response.content[0].text.strip()

    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0].strip()
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        return {
            "faithfulness": 0,
            "relevance": 0,
            "completeness": 0,
            "correctness": 0,
            "reason": f"JSON 解析失败: {response_text[:200]}",
        }


def run_judge_evaluation(
    eval_data: list[dict],
    client: anthropic.Anthropic | None = None,
) -> dict:
    """
    批量运行 LLM-as-Judge 评估。

    参数:
        eval_data: [{
            "question": str,
            "answer": str,
            "contexts": list[str],
            "ground_truth": str,
            "category": str,
        }]

    返回:
    {
        "overall": {"faithfulness": float, "relevance": float, ...},
        "by_category": {...},
        "details": [...]
    }
    """
    if client is None:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    details = []
    scores_by_category = {}

    for item in eval_data:
        context = "\n---\n".join(item["contexts"]) if item["contexts"] else "（无检索结果）"

        scores = judge_answer(
            question=item["question"],
            answer=item["answer"],
            context=context,
            expected_answer=item["ground_truth"],
            client=client,
        )

        cat = item.get("category", "其他")
        if cat not in scores_by_category:
            scores_by_category[cat] = []
        scores_by_category[cat].append(scores)
        details.append({**item, "scores": scores})

    # 计算平均分
    def avg_scores(score_list):
        if not score_list:
            return {}
        dims = ["faithfulness", "relevance", "completeness", "correctness"]
        return {
            dim: sum(s.get(dim, 0) for s in score_list) / len(score_list)
            for dim in dims
        }

    all_scores = [d["scores"] for d in details]

    return {
        "overall": avg_scores(all_scores),
        "by_category": {cat: avg_scores(scores) for cat, scores in scores_by_category.items()},
        "details": details,
    }
