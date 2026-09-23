"""学科特征值模型单测（S2 学科特征值模型移植自灵犀家长端，纯函数模块）。

纯函数模块，无 DB/网络/文件依赖，只测配方合法性 + 金快照一致 + 学科主导 + 元数据：
  1. 每学科 recipe 合法（recipe_is_valid：非空、四 key 全、非负、和=1 容差 1e-6）
  2. 与内嵌实测金快照一致：MEASURED_COUNTS 归一化权重 ≈ profile.nature_recipe（±0.001）
  3. 关键学科主导断言：数学 rule>0.70 / 物理 rule>0.85 / 英语 symbol>0.60 /
     历史 fact>0.90 / 生物 fact>0.50 / 语文 procedure>fact（procedure 主导）
  4. 元数据非空：real_world_image / absorption_skins / curriculum ∈ {k12, dse, mixed}
  5. 覆盖 12 学科；'math' 脏别名不单独建 profile
  6. 接口边界：get_profile 未知学科抛 KeyError（带可选值列表）

注：C 端单测里的「配方可喂 S1 synthetic_student」两项（S1 合成学生生成器）在叙阅 B 端
无对应模块，未移植；配方合法性断言已覆盖其核心约束（四 key 全、非负、和=1）。
"""

import pytest

from app.services.subject_profiles import (
    DATA_SOURCE,
    MEASURED_AT,
    MEASURED_COUNTS,
    NATURE_KEYS,
    RECIPE_VERSION,
    SUBJECT_PROFILES,
    SubjectProfile,
    all_subjects,
    get_profile,
    nature_recipe_for,
    recipe_is_valid,
)


# ── 1. 配方合法性 ───────────────────────────────────────────────────────


class TestRecipeValidity:
    @pytest.mark.parametrize("subject", sorted(SUBJECT_PROFILES))
    def test_recipe_is_valid_for_all_profiles(self, subject):
        """每学科 recipe 都合法：非空、四 key 全、非负、和=1（容差 1e-6）。"""
        recipe = SUBJECT_PROFILES[subject].nature_recipe
        assert recipe_is_valid(recipe), f"{subject} recipe 不合法: {recipe}"
        assert set(recipe) == set(NATURE_KEYS), f"{subject} 四分类 key 不全"
        assert all(w >= 0 for w in recipe.values()), f"{subject} 出现负权重"
        assert abs(sum(recipe.values()) - 1.0) <= 1e-6, f"{subject} 权重和 != 1"

    def test_recipe_is_valid_rejects_empty(self):
        assert recipe_is_valid({}) is False

    def test_recipe_is_valid_rejects_missing_key(self):
        assert recipe_is_valid({"fact": 0.5, "rule": 0.5}) is False

    def test_recipe_is_valid_rejects_negative_weight(self):
        recipe = {"fact": 1.2, "rule": -0.2, "procedure": 0.0, "symbol": 0.0}
        assert recipe_is_valid(recipe) is False

    def test_recipe_is_valid_rejects_bad_sum(self):
        recipe = {"fact": 0.5, "rule": 0.5, "procedure": 0.1, "symbol": 0.1}
        assert recipe_is_valid(recipe) is False

    def test_recipe_is_valid_rejects_non_dict(self):
        assert recipe_is_valid(None) is False
        assert recipe_is_valid("not-a-recipe") is False


# ── 2. 与实测金快照一致 ─────────────────────────────────────────────────


class TestGoldenSnapshot:
    @pytest.mark.parametrize("subject", sorted(SUBJECT_PROFILES))
    def test_recipe_matches_normalized_counts(self, subject):
        """归一化权重（count/total）与 profile.nature_recipe 逐分类一致（±0.001）。"""
        counts = MEASURED_COUNTS[subject]
        total = sum(counts.values())
        profile = SUBJECT_PROFILES[subject]
        assert total == profile.sample_size, f"{subject} sample_size 与金快照不符"
        for nature in NATURE_KEYS:
            expected = counts[nature] / total
            assert profile.nature_recipe[nature] == pytest.approx(expected, abs=0.001), (
                f"{subject}.{nature}: profile={profile.nature_recipe[nature]:.4f} "
                f"实测归一化={expected:.4f}"
            )

    def test_snapshot_subject_keys_match_profiles(self):
        """金快照学科集合 = profile 学科集合 + 'math' 脏别名（不建 profile）。"""
        gold_subjects = set(MEASURED_COUNTS)
        profile_subjects = set(SUBJECT_PROFILES)
        assert profile_subjects <= gold_subjects
        assert gold_subjects - profile_subjects == {"math"}


# ── 3. 关键学科主导断言 ─────────────────────────────────────────────────


class TestSubjectDominance:
    def test_math_rule_dominant(self):
        recipe = get_profile("数学").nature_recipe
        assert recipe["rule"] > 0.70, recipe

    def test_physics_rule_dominant(self):
        recipe = get_profile("物理").nature_recipe
        assert recipe["rule"] > 0.85, recipe

    def test_english_symbol_dominant(self):
        recipe = get_profile("英语").nature_recipe
        assert recipe["symbol"] > 0.60, recipe

    def test_history_fact_dominant(self):
        recipe = get_profile("历史").nature_recipe
        assert recipe["fact"] > 0.90, recipe

    def test_biology_fact_dominant(self):
        recipe = get_profile("生物").nature_recipe
        assert recipe["fact"] > 0.50, recipe

    def test_chinese_procedure_dominant_over_fact(self):
        recipe = get_profile("语文").nature_recipe
        assert recipe["procedure"] > recipe["fact"], recipe


# ── 4. 元数据非空 ──────────────────────────────────────────────────────


class TestProfileMetadata:
    @pytest.mark.parametrize("subject", sorted(SUBJECT_PROFILES))
    def test_metadata_fields(self, subject):
        profile = SUBJECT_PROFILES[subject]
        assert isinstance(profile, SubjectProfile)
        assert profile.subject == subject
        assert isinstance(profile.real_world_image, str) and profile.real_world_image.strip()
        assert isinstance(profile.absorption_skins, list) and profile.absorption_skins
        assert all(isinstance(s, str) and s.strip() for s in profile.absorption_skins)
        assert profile.curriculum in {"k12", "dse", "mixed"}, profile.curriculum
        assert profile.recipe_src in {"measured", "measured+calibrated"}
        assert profile.sample_size > 0

    def test_real_world_image_required(self):
        """真实世界映像方式必须非空 str（设计文档 §二 表字段）。"""
        for subject in all_subjects():
            assert isinstance(SUBJECT_PROFILES[subject].real_world_image, str)
            assert len(SUBJECT_PROFILES[subject].real_world_image) > 1


# ── 5. 覆盖 12 学科 + math 脏别名 ──────────────────────────────────────


class TestCoverage:
    def test_twelve_subjects_covered(self):
        assert len(all_subjects()) == 12

    def test_math_alias_not_a_profile(self):
        subjects = all_subjects()
        assert "math" not in subjects, "math 脏别名不应单独建 profile"
        assert "数学" in subjects
        assert "csd" in subjects

    def test_math_alias_documented_in_snapshot(self):
        # 脏别名保留在快照（verify 脚本做 DB 全量计数比对用），但不建 profile
        assert MEASURED_COUNTS["math"] == {"fact": 0, "rule": 0, "procedure": 1, "symbol": 0}
        assert "math" not in SUBJECT_PROFILES


# ── 6. 接口边界 ────────────────────────────────────────────────────────


class TestInterfaces:
    def test_get_profile_unknown_raises_keyerror_with_options(self):
        with pytest.raises(KeyError) as ei:
            get_profile("不存在的学科")
        assert "数学" in str(ei.value), "KeyError 应带可选值列表"

    def test_nature_recipe_for_returns_dict_copy(self):
        r1 = nature_recipe_for("数学")
        r2 = nature_recipe_for("数学")
        assert r1 == r2
        assert r1 is not SUBJECT_PROFILES["数学"].nature_recipe, "应返回副本"
        r1["rule"] = 0.0
        assert SUBJECT_PROFILES["数学"].nature_recipe["rule"] > 0.8, "外部改不污染常量"

    def test_all_subjects_returns_list(self):
        assert isinstance(all_subjects(), list)
        assert len(all_subjects()) == len(set(all_subjects())), "学科名不重复"

    def test_source_constants(self):
        assert MEASURED_AT == "2026-08-30"
        assert "grade" in DATA_SOURCE
        assert RECIPE_VERSION.startswith("s2-")


class TestChineseNoteAndCalibration:
    def test_chinese_recipe_src_measured_with_note(self):
        """语文配方以实测为准（recipe_src='measured'），差异用 calibration_note 显式标注。"""
        profile = get_profile("语文")
        assert profile.recipe_src == "measured", "语文不擅自校准"
        assert profile.calibration_note is not None
        assert "procedure" in profile.calibration_note
        assert "fact" in profile.calibration_note

    def test_all_measured_recipes_are_not_calibrated(self):
        """S2 全部配方均为纯实测（measured），未做教学法微调校准。"""
        assert all(p.recipe_src == "measured" for p in SUBJECT_PROFILES.values())
