"""科目族路由（《科目分层识别引擎方案 v1.0》S3b 落地）。

一条路由决策点：文件夹 meta.json 的科目元数据优先，缺失/无法映射才用 VL 看图分类兜底；
置信落在灰色区间（GRAY_MIN~GRAY_MAX）强制降级通用通道，规避窄域提示词错配脆化。

family 用途：
- `family_prompt_hint` 拼进判分提示词（按族分流复核策略）；
- blocks 落 `subject_family` 字段，供复核数据按族记账。

纯映射/规则函数可单测；VL 兜底懒 import 千问，失败一律 general。
"""
from __future__ import annotations

FAMILY_MATH = "math"
FAMILY_PHYSICS = "physics"
FAMILY_CHEMISTRY = "chemistry"
FAMILY_LANGUAGE = "language"
FAMILY_GENERAL = "general"

VALID_FAMILIES = (
    FAMILY_MATH,
    FAMILY_PHYSICS,
    FAMILY_CHEMISTRY,
    FAMILY_LANGUAGE,
    FAMILY_GENERAL,
)

# 灰区阈值（方案：置信灰色区间强制降级通用通道）
GRAY_MIN = 0.4
GRAY_MAX = 0.7

# 精确映射：12 学科 + 常见别名。已知但归通用族的学科（生物/历史/…）也在此登记，
# 避免它们被当成「未知科目」白白走 VL 兜底。
_SUBJECT_FAMILY_EXACT: dict[str, str] = {
    "数学": FAMILY_MATH,
    "math": FAMILY_MATH,
    "maths": FAMILY_MATH,
    "物理": FAMILY_PHYSICS,
    "physics": FAMILY_PHYSICS,
    "化学": FAMILY_CHEMISTRY,
    "chemistry": FAMILY_CHEMISTRY,
    "语文": FAMILY_LANGUAGE,
    "语文英语": FAMILY_LANGUAGE,
    "英语": FAMILY_LANGUAGE,
    "英文": FAMILY_LANGUAGE,
    "chinese": FAMILY_LANGUAGE,
    "english": FAMILY_LANGUAGE,
    # 已知学科 → 通用族（不升级专用通道）
    "生物": FAMILY_GENERAL,
    "历史": FAMILY_GENERAL,
    "地理": FAMILY_GENERAL,
    "道德与法治": FAMILY_GENERAL,
    "道法": FAMILY_GENERAL,
    "科学": FAMILY_GENERAL,
    "信息技术": FAMILY_GENERAL,
    "csd": FAMILY_GENERAL,
}

# 包含匹配：兜「小学数学」「数学（人教版）」这类带前后缀的写法。只登记专用族关键词。
_SUBJECT_FAMILY_CONTAINS: tuple[tuple[str, str], ...] = (
    ("数学", FAMILY_MATH),
    ("math", FAMILY_MATH),
    ("物理", FAMILY_PHYSICS),
    ("physics", FAMILY_PHYSICS),
    ("化学", FAMILY_CHEMISTRY),
    ("chemistry", FAMILY_CHEMISTRY),
    ("语文", FAMILY_LANGUAGE),
    ("英语", FAMILY_LANGUAGE),
    ("英文", FAMILY_LANGUAGE),
    ("english", FAMILY_LANGUAGE),
)

_FAMILY_PROMPT_HINTS: dict[str, str] = {
    FAMILY_MATH: "科目族=数学：等价变形与正确的计算过程同样判对，重点核对最终数值与数学符号。",
    FAMILY_PHYSICS: "科目族=物理：关注物理量、单位与公式，结论对即可，过程表述不必逐字一致。",
    FAMILY_CHEMISTRY: "科目族=化学：关注化学式、配平与结论，表达不同但等价即可判对。",
    FAMILY_LANGUAGE: "科目族=语文/英语：语义宽松，意思对即判对，个别错别字不影响判对。",
    FAMILY_GENERAL: "",
}

_FAMILY_CLASSIFY_PROMPT = (
    "你是试卷分类助手。看这张学生试卷图片，判断它属于哪个科目族，只输出一个合法 JSON，"
    "不要 markdown 代码块或其它文字：\n"
    '{"family": "math|physics|chemistry|language|general", "confidence": 0.0~1.0}\n'
    "math=数学（算式/计算/方程），physics=物理，chemistry=化学，"
    "language=语文或英语（语言文字/阅读/作文），general=其余或看不清。"
)


def _match_family(subject: str) -> str | None:
    """科目字符串 → family；无法映射返回 None（区别于「已知但归 general」）。"""
    s = (subject or "").strip()
    if not s:
        return None
    low = s.lower()
    for key, fam in _SUBJECT_FAMILY_EXACT.items():
        if low == key.lower():
            return fam
    for key, fam in _SUBJECT_FAMILY_CONTAINS:
        if key.lower() in low:
            return fam
    return None


def resolve_family(subject: str) -> str:
    """科目字符串 → family；空/未知 → general（通用通道缺省）。"""
    return _match_family(subject) or FAMILY_GENERAL


def subject_known(subject: str) -> bool:
    """科目是否能映射（含已知但归 general 的学科，如生物）。"""
    return _match_family(subject) is not None


def family_prompt_hint(family: str) -> str:
    """按族返回判分提示词附加语；general/未知返回空串（不改提示词行为）。"""
    return _FAMILY_PROMPT_HINTS.get(str(family or "").strip().lower(), "")


def family_from_confidence(family: str, confidence: float) -> str:
    """VL 分类结果过灰区门槛：置信 ∈ [GRAY_MIN, GRAY_MAX]（闭区间）及以下一律强制 general。"""
    fam = str(family or "").strip().lower()
    if fam not in VALID_FAMILIES:
        return FAMILY_GENERAL
    try:
        conf = float(confidence)
    except (TypeError, ValueError):
        return FAMILY_GENERAL
    return fam if conf > GRAY_MAX else FAMILY_GENERAL


def _json_object_from_text(text: str) -> dict:
    """从模型输出里抠出第一个 JSON 对象（容错 markdown 围栏/前后废话）。"""
    import json
    import re

    raw = (text or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if m:
        raw = m.group(1).strip()
    start = raw.find("{")
    if start == -1:
        return {}
    depth = 0
    for i in range(start, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(raw[start : i + 1])
                    return data if isinstance(data, dict) else {}
                except json.JSONDecodeError:
                    return {}
    return {}


def classify_family_with_vl(image_path: str) -> tuple[str, float]:
    """VL 兜底：看图定科目族。失败返回 ("general", 0.0)。"""
    try:
        from PIL import Image

        from app.grading.pipeline import _get_openai_client, _pil_image_to_data_url
        from app.utils.qwen_settings import get_vl_model

        client = _get_openai_client()
        with Image.open(image_path) as im:
            url = _pil_image_to_data_url(im.convert("RGB"))
        completion = client.chat.completions.create(
            model=get_vl_model(),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": url}},
                        {"type": "text", "text": _FAMILY_CLASSIFY_PROMPT},
                    ],
                }
            ],
            stream=False,
            extra_body={"enable_thinking": False},
        )
        text = (completion.choices[0].message.content or "").strip()
        data = _json_object_from_text(text)
        fam = str(data.get("family") or "").strip().lower()
        if fam not in VALID_FAMILIES:
            return FAMILY_GENERAL, 0.0
        try:
            conf = max(0.0, min(1.0, float(data.get("confidence"))))
        except (TypeError, ValueError):
            conf = 0.0
        return fam, conf
    except Exception:
        return FAMILY_GENERAL, 0.0


def resolve_family_with_fallback(subject: str, image_path: str | None = None) -> tuple[str, str]:
    """科目族判定（单一决策点）：meta 优先 → VL 兜底 → 缺省 general。

    返回 (family, source)，source ∈ {"meta", "vl", "default"}。
    """
    matched = _match_family(subject)
    if matched is not None:
        return matched, "meta"
    if image_path:
        fam, conf = classify_family_with_vl(image_path)
        return family_from_confidence(fam, conf), "vl"
    return FAMILY_GENERAL, "default"
