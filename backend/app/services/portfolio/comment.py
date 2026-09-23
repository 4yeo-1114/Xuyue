"""
学期报告 AI 评语服务（A0 §7）：AI 生成 + 教师确认 + 禁词闸门 fail-closed。

学术安全线：
  - LLM 输出必须过 FORBIDDEN_WORDS 闸门：含人格归因词 → 清洗（去掉含禁止词的句子），
    清洗后为空 → 兜底文案；绝不原样落库。
  - 教师确认改文同样过闸门（确认端点 422 拒绝）。
  - 评语只进 assessment_comment 表 / report_snapshot.payload，绝不写 student_portfolio.dimensions
    或参与五育综合分。
"""
from __future__ import annotations

import re
from typing import Optional

from app.utils.anonymize import Anonymizer

# 网关失败 / 词表清洗后为空的兜底文案（状态 ai_failed 时展示）
FALLBACK_COMMENT = "本学期学业评语暂未生成，请联系班主任当面沟通孩子的成长情况。"

# ── 人格归因禁止词（AI 输出 + 教师人工输入均拦截；A0 §7 权威清单）──────────
FORBIDDEN_WORDS: list[str] = [
    "粗心", "马虎", "懒惰", "懒散", "态度差", "态度不端正",
    "性格缺陷", "性格问题", "内向", "孤僻", "多动", "好动",
    "注意力不集中", "笨", "迟钝", "智商", "天赋差", "不是读书的料",
    "没救了", "差生", "后进生",
]


# ── S2 学科特征值模型注入（subject_profiles.py）──────────────────────────
# 把「学科知识本质四分类配方 × 真实世界映像 × 最佳吸收皮」作为策略上下文
# 附加到评语 prompt，让评语中的学习建议贴合学科本质。
_NATURE_LABELS = {
    "fact": "事实记忆",
    "rule": "规律/概念理解",
    "procedure": "操作/程序技能",
    "symbol": "符号/语言形式",
}


def _subject_strategy_context(subject: Optional[str]) -> str:
    """S2 学科特征值模型 → 评语 prompt 的学科本质策略段（缺失/未知学科返回空串）。

    纯函数：只读 subject_profiles 常量，不碰 DB/网络；未知学科静默跳过，
    不改变现有（无学科）评语生成行为。
    """
    if not subject:
        return ""
    try:
        from app.services.subject_profiles import get_profile
        profile = get_profile(subject)
    except Exception:
        return ""
    dominant = max(profile.nature_recipe.items(), key=lambda kv: kv[1])[0]
    label = _NATURE_LABELS.get(dominant, dominant)
    recipe_str = "、".join(f"{k} {v:.2f}" for k, v in profile.nature_recipe.items())
    skins = "、".join(profile.absorption_skins) if profile.absorption_skins else "常规"
    return (
        f"六、学科知识本质策略（{subject}）：该学科以「{label}」型知识为主导"
        f"（四类占比 {recipe_str}），真实世界映像为「{profile.real_world_image}」，"
        f"最佳吸收皮为「{skins}」。若评语涉及该学科学习建议，请贴合这一学科本质"
        f"给出练习方式建议（侧重{label}类内容，优先用「{skins}」方式呈现与训练）。"
    )


def sanitize_comment(text) -> tuple[str, bool]:
    """词表闸门（fail-closed）：含禁止词 → 清洗（去掉含禁止词的句子）；清洗后为空 → 兜底。

    返回 (content, flagged)。
      - flagged=True 表示内容曾被闸门拦截/清洗（调用方记录 gate_flagged 供审计）。
      - 绝不含禁止词原文返回。
    """
    if not text or not isinstance(text, str):
        return FALLBACK_COMMENT, True
    text = text.strip()
    if not text:
        return FALLBACK_COMMENT, True

    # 按中文/英文句读切分，保留分隔符
    sentences = re.split(r"(?<=[。！？!?；;])", text)
    cleaned: list[str] = []
    flagged = False
    for s in sentences:
        if any(w in s for w in FORBIDDEN_WORDS):
            flagged = True
            continue
        cleaned.append(s)
    result = "".join(cleaned).strip()
    if not result:
        return FALLBACK_COMMENT, True
    # 兜底：即使清洗后仍可能残留单个禁止词（极端拆分），再整体校验一次
    if any(w in result for w in FORBIDDEN_WORDS):
        return FALLBACK_COMMENT, True
    return result, flagged


def build_comment_messages(report: dict, anon: Optional[Anonymizer] = None,
                           subject: Optional[str] = None) -> list[dict]:
    """基于报告数据组装 LLM 学业评语 messages（智育指标 / 五育 / 标签 / 趋势）。

    E08 · PII 防护：拼 prompt 前把学生真名经 Anonymizer 匿名化（学生01），
    消除把学生真名发给第三方模型的合规缺口。输出侧还原由调用方持同一 anon 完成；
    sanitize_comment 禁词闸门保留。

    S2 注入：subject 提供且能命中 subject_profiles 配方时，附加该学科的知识本质策略段
    （吸收皮 × 映像方式），让评语学习建议贴合学科本质；缺失/未知学科静默跳过。
    学期评语为五育整体画像，默认无单一 subject 维度，由调用方按需传入。
    """
    anon = anon or Anonymizer()
    name = report.get("name") or "该学生"
    anon_name = anon.anon(name)  # 登记真名并取匿名标识（学生01）
    grade = report.get("grade") or ""
    term = report.get("term") or ""
    dims = report.get("dimensions") or {}
    data_status = report.get("data_status") or {}
    baseline = report.get("baseline") or {}
    profile = report.get("assessment_profile") or {}
    labels = profile.get("labels") or []
    milestones = report.get("milestones") or []

    intel = (dims.get("intellectual") or {})
    intel_detail = intel.get("detail") or {}
    intel_status = data_status.get("intellectual") or "insufficient"

    detail_lines = [
        f"订正错题 {intel_detail.get('corrected_wrong_questions', 0)} 道",
        f"考试成绩提升 {intel_detail.get('rank_improvements', 0)} 次",
        f"生成靶向提升报告 {intel_detail.get('targeted_reports', 0)} 份",
        f"超班级均分 {intel_detail.get('above_class_avg', 0)} 次",
        f"攻克薄弱点 {intel_detail.get('weak_point_conquered', 0)} 次",
    ]
    baseline_lines: list[str] = []
    comp = (baseline.get("composite") or {}).get("intellectual")
    tier = (baseline.get("tier") or {}).get("intellectual")
    percentile = (baseline.get("percentile") or {}).get("intellectual")
    if comp is not None:
        baseline_lines.append(f"智育综合分 {comp:.1f}（满分 100）")
    if tier:
        baseline_lines.append(f"档位 {tier}")
    if percentile is not None:
        baseline_lines.append(f"班级百分位 P{percentile:.0f}")

    ms_lines = []
    for m in milestones[:5]:
        name_m = m.get("name") or m.get("event_type")
        when = m.get("occurred_at")
        if when:
            when_s = when.strftime("%m-%d") if hasattr(when, "strftime") else str(when)[:10]
            ms_lines.append(f"{when_s} {name_m}")
        else:
            ms_lines.append(name_m)

    dim_status_lines = [
        f"{dim}：{'已有数据' if data_status.get(dim) == 'has_data' else '数据待补充'}"
        for dim in ("moral", "intellectual", "physical", "aesthetic", "labor", "ai_literacy")
    ]

    system = (
        "你是一位经验丰富的班主任，负责撰写学生学期学业评语。"
        "要求：\n"
        "1. 基于给定的学期成长数据，客观描述孩子的学习过程与行为表现；\n"
        "2. 语言正向、具体、有温度，多用行为观察（如「本学期坚持订正错题」），"
        "少用抽象评价；\n"
        "3. 严禁人格归因与贴标签：不得出现「粗心」「懒惰」「态度差」「性格缺陷」"
        "「内向」「多动」等字眼；不得对孩子的智力、性格、品行做定性判断；\n"
        "4. 篇幅 150~220 字，结尾给 1~2 条可执行的成长建议；\n"
        "5. 直接输出评语正文，不要加标题或引号。"
    )

    user_parts = [
        f"学生姓名：{anon_name}；年级：{grade or '未知'}；学期：{term}",
        "一、五育数据状态：" + "；".join(dim_status_lines),
        f"二、智育表现（{intel_status}）：" + "；".join(detail_lines),
    ]
    if baseline_lines:
        user_parts.append("三、班级相对位置（归一化基准线）：" + "；".join(baseline_lines))
    if ms_lines:
        user_parts.append("四、本学期里程碑：" + "；".join(ms_lines))
    if labels:
        user_parts.append("五、行为画像白名单标签：" + "、".join(labels))
    else:
        user_parts.append("五、行为画像：暂无测评标签（不虚构）。")

    subject_ctx = _subject_strategy_context(subject)
    if subject_ctx:
        user_parts.append(subject_ctx)

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(user_parts)},
    ]
