"""正则元数据提取器

从政策文档文本中提取结构化元数据：文号、日期、发文机关、适用地区、类别等。
政府公文格式相对规范，正则可以覆盖大部分场景。
"""

import re


# 已知的发文机关关键词（用于从文号中提取或从正文中匹配）
KNOWN_AUTHORITIES = [
    "国务院", "国务院办公厅",
    "工业和信息化部", "工信部",
    "财政部", "科技部", "教育部", "人力资源社会保障部", "人社部",
    "商务部", "农业农村部", "自然资源部", "生态环境部",
    "交通运输部", "住房城乡建设部", "水利部", "文化和旅游部",
    "国家卫生健康委", "国家发展改革委", "发改委",
    "国家税务总局", "海关总署", "市场监管总局",
    "国家统计局", "国家知识产权局", "国家药监局",
    "中国人民银行", "金融监管总局", "证监会",
    "国家中医药局", "国家民委", "国务院国资委",
]

# 政策分类关键词映射
CATEGORY_KEYWORDS = {
    "融资支持": ["贷款", "贴息", "融资", "信贷", "担保", "投资", "基金"],
    "税收优惠": ["税收", "减税", "免税", "退税", "税率", "增值税", "所得税"],
    "人才政策": ["人才", "人力资源", "就业", "培训", "社保", "年金", "薪酬"],
    "产业扶持": ["产业", "制造", "工业", "互联网", "升级", "培育", "发展"],
    "科技创新": ["科技", "创新", "研发", "专利", "技术", "人工智能", "数字化"],
}


def _normalize_date(date_str: str) -> str | None:
    """将中文日期标准化为 YYYY-MM-DD 格式"""
    # 去掉空格
    date_str = re.sub(r"\s+", "", date_str)
    match = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", date_str)
    if match:
        y, m, d = match.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"
    return None


def _extract_policy_number(text: str) -> str | None:
    """
    提取发文字号
    格式：XX〔2024〕N号 或 XX[2024]N号
    例：工信部联企业〔2024〕1号、财金〔2026〕15号
    """
    # 取前 500 字（文号通常在开头）
    head = text[:500]
    pattern = r"[^\s,，。；\n〔\[]{2,20}[〔\[]\d{4}[〕\]]\d+号"
    match = re.search(pattern, head)
    if match:
        return match.group().strip()
    return None


def _extract_issuing_authority(text: str, policy_number: str | None) -> str | None:
    """提取发文机关"""
    # 优先从文号中提取
    if policy_number:
        # "工信部联企业〔2024〕1号" → "工信部联企业" → 匹配到 "工信部"
        prefix = re.match(r"(.+?)[〔\[]", policy_number)
        if prefix:
            pn_authority = prefix.group(1)
            # 在已知机关列表中查找
            for authority in KNOWN_AUTHORITIES:
                if authority in pn_authority:
                    return authority
            # 文号前缀不在已知列表中，继续往下从正文匹配

    # 从正文前 500 字中匹配已知机关
    head = text[:500]
    for authority in KNOWN_AUTHORITIES:
        if authority in head:
            return authority

    # 从"发布来源"行提取
    match = re.search(r"发布来源[:：]\s*(.+)", text[:300])
    if match:
        return match.group(1).strip()

    return None


def _extract_publish_date(text: str) -> str | None:
    """提取发布日期（通常在文档末尾的落款处）"""
    # 取后 500 字
    tail = text[-500:]

    # 匹配：XXXX年X月X日
    dates = re.findall(r"(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)", tail)
    if dates:
        # 取最后一个日期（通常是落款日期）
        return _normalize_date(dates[-1])

    # 也试试前面（有些文档日期在开头）
    head = text[:500]
    dates = re.findall(r"(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)", head)
    if dates:
        return _normalize_date(dates[0])

    return None


def _extract_effective_date(text: str) -> str | None:
    """提取生效日期"""
    patterns = [
        r"自(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)起施行",
        r"自(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)起执行",
        r"自(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)起实施",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _normalize_date(match.group(1))
    return None


def _extract_expiry_date(text: str) -> str | None:
    """提取失效日期"""
    patterns = [
        r"有效期至(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)",
        r"执行至(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)",
        r"有效期.*?(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)止",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _normalize_date(match.group(1))
    return None


def _extract_applicable_region(text: str) -> str | None:
    """提取适用地区"""
    head = text[:500]

    # 全国性文件的标志
    if re.search(r"各省、自治区|全国|各地区", head):
        return "全国"

    # 尝试匹配具体地区（必须是行首或紧跟在空格后的完整地名）
    region = re.search(r"(?:^|\s)([\u4e00-\u9fa5]{2,6}(?:省|自治区|直辖市))", head)
    if region:
        return region.group(1)

    return None


def _extract_title(text: str) -> str | None:
    """从文本中提取标题（通常是第一个有意义的行）"""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    for line in lines:
        # 跳过日期行、机关名
        if re.match(r"^\d{4}年", line):
            continue
        if len(line) < 5:
            continue
        # 标题通常是"关于XXX的通知/办法/意见"
        if re.search(r"关于|办法|通知|意见|方案|规定|条例|公告|计划", line):
            return line
        # 或者第一个超过10字的行
        if len(line) >= 10:
            return line
    return None


def _classify_category(text: str, title: str = "") -> str | None:
    """根据关键词对政策进行分类"""
    combined = title + " " + text[:1000]

    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score > 0:
            scores[category] = score

    if scores:
        return max(scores, key=scores.get)
    return "其他"


def extract_metadata_by_regex(text: str) -> dict:
    """
    从政策文档文本中提取元数据。

    参数:
        text: 文档全文

    返回（缺失字段为 None）:
    {
        "title": str | None,
        "policy_number": str | None,
        "issuing_authority": str | None,
        "publish_date": str | None,
        "effective_date": str | None,
        "expiry_date": str | None,
        "applicable_region": str | None,
        "category": str | None,
    }
    """
    policy_number = _extract_policy_number(text)

    return {
        "title": _extract_title(text),
        "policy_number": policy_number,
        "issuing_authority": _extract_issuing_authority(text, policy_number),
        "publish_date": _extract_publish_date(text),
        "effective_date": _extract_effective_date(text),
        "expiry_date": _extract_expiry_date(text),
        "applicable_region": _extract_applicable_region(text),
        "category": _classify_category(text),
    }


def get_missing_fields(metadata: dict) -> list[str]:
    """返回值为 None 的字段列表"""
    return [k for k, v in metadata.items() if v is None]
