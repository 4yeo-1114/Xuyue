"""学科特征值模型 — 每学科知识本质四分类配方 × 真实世界映像 × 最佳吸收皮（S2）

承接 docs/plans/synthetic-student-sim-design-20260830.md §二 / S2：
在 S1 合成学生生成器（synthetic_student.py，学段级 nature_recipe）之上，
把配方从学段级细化到学科级——每学科一个 SubjectProfile：
  - nature_recipe:     knowledge_nature 四分类权重（fact/rule/procedure/symbol，和=1）
                       = 实测计数归一化（2026-08-30 灵犀 PG grade 库只读聚合，保留 3 位小数）
  - real_world_image:  该学科的真实世界映像方式（设计文档 §二 表）
  - absorption_skins:  该学科的最佳吸收皮（设计文档 §二 表，list）
  - recipe_src:        "measured"（纯实测）/ "measured+calibrated"（实测为主教学法微调）
  - calibration_note:  与教学法示意不一致的差异说明（可选）

学科归属：knowledge_points.unit_id -> subject_units.subject（实测 100% 覆盖，0 orphan）。
脏别名：'math' 单例（n=1 procedure）为脏别名，归并进「数学」，不单独建 profile，
  在 MEASURED_COUNTS 快照中保留（供 verify 脚本做 DB 全量计数比对），SUBJECT_PROFILES 不含它。

纯函数铁律：不 import app 的 DB/模型，不读文件，不碰网络。
金数据（2026-08-30 只读实测聚合）内嵌为模块常量 MEASURED_COUNTS，不连库。

recipe 结构与 S1 的 nature_recipe 同构（四分类 dict），可无缝喂给
SyntheticStudentGenerator._validate_recipe / _sample_nature。

示例：
    >>> p = get_profile("数学")
    >>> p.nature_recipe["rule"]
    0.847
    >>> nature_recipe_for("物理")["rule"] > 0.85
    True
    >>> "math" in all_subjects()
    False
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ── 溯源常量 ──────────────────────────────────────────────────────────────
MEASURED_AT = "2026-08-30"
DATA_SOURCE = "灵犀 PG grade 库只读聚合（knowledge_points × subject_units）"
RECIPE_VERSION = "s2-subject-profiles-v1"

# knowledge_nature 四分类键（与 S1 synthetic_student 的 nature_recipe 同构）
NATURE_KEYS = ("fact", "rule", "procedure", "symbol")

# ── 实测金快照（2026-08-30 只读聚合，作内嵌常量，不连库）──────────────────
# SQL: SELECT su.subject, kp.knowledge_nature, count(*)
#      FROM knowledge_points kp JOIN subject_units su ON kp.unit_id = su.id
#      WHERE kp.knowledge_nature IS NOT NULL GROUP BY 1, 2
# 注意：GROUP BY 只回非零计数，快照里缺失分类补 0，保证四 key 齐全。
MEASURED_COUNTS: dict[str, dict[str, int]] = {
    "数学": {"fact": 4, "rule": 183, "procedure": 27, "symbol": 2},
    "物理": {"fact": 0, "rule": 214, "procedure": 17, "symbol": 0},
    "化学": {"fact": 21, "rule": 31, "procedure": 13, "symbol": 2},
    "生物": {"fact": 1392, "rule": 624, "procedure": 159, "symbol": 10},
    "语文": {"fact": 26, "rule": 22, "procedure": 112, "symbol": 29},
    "英语": {"fact": 9, "rule": 20, "procedure": 108, "symbol": 298},
    "历史": {"fact": 211, "rule": 0, "procedure": 1, "symbol": 0},
    "地理": {"fact": 165, "rule": 97, "procedure": 12, "symbol": 0},
    "道德与法治": {"fact": 73, "rule": 47, "procedure": 6, "symbol": 0},
    "科学": {"fact": 43, "rule": 47, "procedure": 13, "symbol": 0},
    "信息技术": {"fact": 5, "rule": 8, "procedure": 15, "symbol": 0},
    "csd": {"fact": 11, "rule": 7, "procedure": 0, "symbol": 0},
    # 脏别名：'math' 单例（n=1 procedure）归并进「数学」，不单独建 profile。
    # 仅保留在快照里供 verify 脚本做 DB 全量计数比对（含脏别名），SUBJECT_PROFILES 不含它。
    "math": {"fact": 0, "rule": 0, "procedure": 1, "symbol": 0},
}


@dataclass(frozen=True)
class SubjectProfile:
    """单学科特征值模型：四分类配方 × 真实世界映像 × 最佳吸收皮。

    nature_recipe 与 S1 synthetic_student 的 nature_recipe 同构（四分类 dict，和=1），
    可直接喂给 SyntheticStudentGenerator._validate_recipe / _sample_nature。
    """

    subject: str
    nature_recipe: dict[str, float]
    sample_size: int
    curriculum: str  # "k12" / "dse" / "mixed"
    real_world_image: str
    absorption_skins: list[str]
    recipe_src: str  # "measured"（纯实测）/ "measured+calibrated"（实测为主教学法微调）
    calibration_note: Optional[str] = None


def _normalize_counts(counts: dict[str, int]) -> dict[str, float]:
    """四分类计数 → 权重（保留 3 位小数，和=1，最大余数法）。

    直接 round 到 3 位小数可能使和 != 1（如生物 0.637+0.286+0.073+0.005=1.001），
    用最大余数法把差额（deficit 个 0.001）分配给小数余数最大的分类，保证 sum == 1.000。
    """
    total = float(sum(counts.values()))
    if total <= 0:
        raise ValueError(f"分类计数和必须 > 0: {counts}")
    raw = {k: counts[k] / total for k in NATURE_KEYS}
    floor3 = {k: int(raw[k] * 1000) / 1000.0 for k in NATURE_KEYS}
    deficit = int(round((1.0 - sum(floor3.values())) * 1000))
    order = sorted(NATURE_KEYS, key=lambda k: raw[k] - floor3[k], reverse=True)
    result = dict(floor3)
    for k in order[:deficit]:
        result[k] = round(result[k] + 0.001, 3)
    return result


# ── 学科元数据（真实世界映像 × 最佳吸收皮，设计文档 §二 表 + 用户补充）─────
# 配方一律数据驱动（实测计数归一化），recipe_src="measured" 不擅自校准；
# 与教学法示意有出入的学科用 calibration_note 显式标注，待老师口径抽查拍板。
_SUBJECT_META: dict[str, dict[str, object]] = {
    "数学": {
        "curriculum": "mixed",
        "real_world_image": "数量/几何关系（分披萨→分数、推车→位移）",
        "absorption_skins": ["变式", "可视化", "图式"],
        "recipe_src": "measured",
        "calibration_note": None,
    },
    "物理": {
        "curriculum": "k12",
        "real_world_image": "力学现象",
        "absorption_skins": ["故事", "实验类比", "变式"],
        "recipe_src": "measured",
        "calibration_note": None,
    },
    "化学": {
        "curriculum": "k12",
        "real_world_image": "物质变化现象",
        "absorption_skins": ["故事", "实验类比", "变式"],
        "recipe_src": "measured",
        "calibration_note": None,
    },
    "生物": {
        "curriculum": "k12",
        "real_world_image": "生命现象",
        "absorption_skins": ["图像联想", "类比"],
        "recipe_src": "measured",
        "calibration_note": "样本 n=2185 远超他科（fact 主 0.637），需老师确认是否因 KP 挂载密度高导致分布偏移",
    },
    "语文": {
        "curriculum": "mixed",
        "real_world_image": "语言生活应用/文本世界",
        "absorption_skins": ["复述", "故事", "写作"],
        "recipe_src": "measured",
        "calibration_note": "实测 procedure 主（0.593，字词书写/读写技能）vs 设计示意 fact 主，两者冲突 → 配方以实测为准，待老师口径抽查拍板",
    },
    "英语": {
        "curriculum": "mixed",
        "real_world_image": "交际情境（对话/生活场景）",
        "absorption_skins": ["情境输入", "韵律", "复述"],
        "recipe_src": "measured",
        "calibration_note": "实测 symbol 主 0.685、fact 仅 0.021（设计示意 symbol 主+fact 辅），fact 偏低待老师口径确认",
    },
    "历史": {
        "curriculum": "k12",
        "real_world_image": "时间线/空间/社会规范",
        "absorption_skins": ["记忆锚点", "思维导图"],
        "recipe_src": "measured",
        "calibration_note": "fact 0.995 几乎纯事实记忆，procedure 仅 1 条，是否合理待老师口径确认",
    },
    "地理": {
        "curriculum": "k12",
        "real_world_image": "时间线/空间/社会规范",
        "absorption_skins": ["记忆锚点", "思维导图"],
        "recipe_src": "measured",
        "calibration_note": None,
    },
    "道德与法治": {
        "curriculum": "k12",
        "real_world_image": "时间线/空间/社会规范",
        "absorption_skins": ["记忆锚点", "思维导图"],
        "recipe_src": "measured",
        "calibration_note": None,
    },
    "科学": {
        "curriculum": "k12",
        "real_world_image": "自然现象探索",
        "absorption_skins": ["实验", "可视化", "变式"],
        "recipe_src": "measured",
        "calibration_note": None,
    },
    "信息技术": {
        "curriculum": "k12",
        "real_world_image": "工具操作与编程",
        "absorption_skins": ["演示", "实操", "项目"],
        "recipe_src": "measured",
        "calibration_note": "样本 n=28 偏小，procedure 主 0.536，待老师口径确认",
    },
    "csd": {
        "curriculum": "dse",
        "real_world_image": "香港社会议题",
        "absorption_skins": ["概念递进"],
        "recipe_src": "measured",
        "calibration_note": "DSE 香港社会议题，fact 0.611 + rule 0.389；样本 n=18 偏小",
    },
}

# ── 每学科一个 profile（frozen dataclass，共 12 个：11 学科 + 数学；含 csd）──
# 'math' 脏别名归并进「数学」，不单独建 profile。
SUBJECT_PROFILES: dict[str, SubjectProfile] = {
    subject: SubjectProfile(
        subject=subject,
        nature_recipe=_normalize_counts(MEASURED_COUNTS[subject]),
        sample_size=sum(MEASURED_COUNTS[subject].values()),
        curriculum=str(meta["curriculum"]),
        real_world_image=str(meta["real_world_image"]),
        absorption_skins=list(meta["absorption_skins"]),  # type: ignore[arg-type]
        recipe_src=str(meta["recipe_src"]),
        calibration_note=meta["calibration_note"],  # type: ignore[arg-type]
    )
    for subject, meta in _SUBJECT_META.items()
}


# ── 对外接口 ─────────────────────────────────────────────────────────────


def all_subjects() -> list[str]:
    """全部学科（含 csd，不含 'math' 脏别名）。"""
    return list(SUBJECT_PROFILES)


def get_profile(subject: str) -> SubjectProfile:
    """取单学科 profile；未知学科抛 KeyError 并带可选值列表。"""
    if subject not in SUBJECT_PROFILES:
        raise KeyError(
            f"未知学科: {subject!r}，可选: {sorted(SUBJECT_PROFILES)}"
        )
    return SUBJECT_PROFILES[subject]


def nature_recipe_for(subject: str) -> dict[str, float]:
    """取单学科四分类配方（返回副本，外部改不污染常量）。"""
    return dict(get_profile(subject).nature_recipe)


def recipe_is_valid(recipe: dict[str, float]) -> bool:
    """配方合法性：非空 dict、四 key 全含、权重非负、和≈1（容差 1e-6）。

    与 S1 SyntheticStudentGenerator._validate_recipe 同一套约束，可作前置校验。
    """
    if not recipe or not isinstance(recipe, dict):
        return False
    if set(recipe) != set(NATURE_KEYS):
        return False
    if any(not isinstance(w, (int, float)) or w < 0 for w in recipe.values()):
        return False
    return abs(sum(recipe.values()) - 1.0) <= 1e-6
