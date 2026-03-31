"""LLM 元数据提取器（兜底）

当正则提取器无法提取某些字段时，使用 Claude Haiku 从文本中提取。
仅在有缺失字段时调用，控制成本。
"""

import json

import anthropic

import config


EXTRACT_PROMPT = """从以下政策文档中提取元数据，以 JSON 格式返回。

只需要提取以下缺失字段：{missing_fields}

字段说明：
- title: 政策文件标题（如"关于实施中小微企业贷款贴息政策的通知"）
- policy_number: 发文字号（如"国办发〔2024〕15号"、"财金〔2026〕15号"）
- issuing_authority: 发文机关（如"财政部"、"工信部"）
- publish_date: 发布日期，格式 YYYY-MM-DD
- effective_date: 生效日期，格式 YYYY-MM-DD
- expiry_date: 失效/废止日期，格式 YYYY-MM-DD
- applicable_region: 适用地区（"全国" 或具体省市）
- category: 政策类别，从以下选择：融资支持/税收优惠/人才政策/产业扶持/科技创新/其他

规则：
- 找不到的字段填 null
- 不要猜测，只提取文档中明确写出的信息
- 日期统一为 YYYY-MM-DD 格式
- 只返回 JSON，不要其他文字

文档内容（前1000字）：
{head_text}

文档结尾（后500字）：
{tail_text}"""


def extract_metadata_by_llm(
    text: str,
    missing_fields: list[str],
    client: anthropic.Anthropic | None = None,
) -> dict:
    """
    用 Haiku 提取正则缺失的元数据字段。

    参数:
        text: 文档全文
        missing_fields: 需要提取的字段名列表
        client: Anthropic 客户端（可选，用于测试注入）

    返回: 提取到的元数据字典（只包含 missing_fields 中的字段）
    """
    if not missing_fields:
        return {}

    if client is None:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    head_text = text[:1000]
    tail_text = text[-500:] if len(text) > 500 else text

    prompt = EXTRACT_PROMPT.format(
        missing_fields=", ".join(missing_fields),
        head_text=head_text,
        tail_text=tail_text,
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = response.content[0].text.strip()

    # 尝试解析 JSON（可能被包在 ```json ``` 中）
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0].strip()
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0].strip()

    try:
        result = json.loads(response_text)
    except json.JSONDecodeError:
        return {}

    # 只返回 missing_fields 中的字段，且值不为 null/None
    return {k: v for k, v in result.items() if k in missing_fields and v is not None}
