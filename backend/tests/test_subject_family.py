import unittest

from app.grading.subject_family import (
    FAMILY_CHEMISTRY,
    FAMILY_GENERAL,
    FAMILY_LANGUAGE,
    FAMILY_MATH,
    FAMILY_PHYSICS,
    family_from_confidence,
    family_prompt_hint,
    resolve_family,
    resolve_family_with_fallback,
    subject_known,
)


class ResolveFamilyTests(unittest.TestCase):
    def test_specialized_families(self):
        self.assertEqual(resolve_family("数学"), FAMILY_MATH)
        self.assertEqual(resolve_family("物理"), FAMILY_PHYSICS)
        self.assertEqual(resolve_family("化学"), FAMILY_CHEMISTRY)
        self.assertEqual(resolve_family("语文"), FAMILY_LANGUAGE)
        self.assertEqual(resolve_family("英语"), FAMILY_LANGUAGE)

    def test_general_families(self):
        for subject in ("生物", "历史", "地理", "道德与法治", "道法", "科学", "信息技术", "csd"):
            self.assertEqual(resolve_family(subject), FAMILY_GENERAL, subject)

    def test_empty_and_unknown(self):
        self.assertEqual(resolve_family(""), FAMILY_GENERAL)
        self.assertEqual(resolve_family("   "), FAMILY_GENERAL)
        self.assertEqual(resolve_family("占星术"), FAMILY_GENERAL)

    def test_aliases_and_suffixes(self):
        self.assertEqual(resolve_family("math"), FAMILY_MATH)
        self.assertEqual(resolve_family("Math"), FAMILY_MATH)
        self.assertEqual(resolve_family("小学数学"), FAMILY_MATH)
        self.assertEqual(resolve_family("数学（人教版）"), FAMILY_MATH)
        self.assertEqual(resolve_family("english"), FAMILY_LANGUAGE)

    def test_subject_known_distinguishes_unknown(self):
        self.assertTrue(subject_known("数学"))
        self.assertTrue(subject_known("生物"))  # 已知但归 general
        self.assertFalse(subject_known("占星术"))
        self.assertFalse(subject_known(""))


class FamilyHintTests(unittest.TestCase):
    def test_math_and_language_hints_nonempty(self):
        self.assertIn("数学", family_prompt_hint(FAMILY_MATH))
        self.assertIn("语义宽松", family_prompt_hint(FAMILY_LANGUAGE))

    def test_general_hint_empty(self):
        self.assertEqual(family_prompt_hint(FAMILY_GENERAL), "")
        self.assertEqual(family_prompt_hint("unknown"), "")

    def test_hint_can_be_appended(self):
        hint = family_prompt_hint(FAMILY_MATH)
        prompt = f"基础提示词。\n\n【科目族提示】{hint}"
        self.assertIn("等价变形", prompt)


class GrayZoneTests(unittest.TestCase):
    def test_gray_zone_forces_general(self):
        """置信 0.5 落灰区（0.4~0.7）→ 强制 general。"""
        self.assertEqual(family_from_confidence(FAMILY_MATH, 0.5), FAMILY_GENERAL)
        self.assertEqual(family_from_confidence(FAMILY_MATH, 0.4), FAMILY_GENERAL)
        self.assertEqual(family_from_confidence(FAMILY_MATH, 0.7), FAMILY_GENERAL)

    def test_low_confidence_forces_general(self):
        self.assertEqual(family_from_confidence(FAMILY_MATH, 0.2), FAMILY_GENERAL)

    def test_high_confidence_keeps_family(self):
        self.assertEqual(family_from_confidence(FAMILY_MATH, 0.71), FAMILY_MATH)
        self.assertEqual(family_from_confidence(FAMILY_PHYSICS, 0.9), FAMILY_PHYSICS)

    def test_invalid_family_or_confidence(self):
        self.assertEqual(family_from_confidence("astrology", 0.99), FAMILY_GENERAL)
        self.assertEqual(family_from_confidence(FAMILY_MATH, "high"), FAMILY_GENERAL)
        self.assertEqual(family_from_confidence(FAMILY_MATH, None), FAMILY_GENERAL)


class FallbackTests(unittest.TestCase):
    def test_meta_wins_no_vl_needed(self):
        fam, source = resolve_family_with_fallback("数学", "Z:\\not\\exist.png")
        self.assertEqual(fam, FAMILY_MATH)
        self.assertEqual(source, "meta")

    def test_known_general_subject_no_vl(self):
        fam, source = resolve_family_with_fallback("生物", "Z:\\not\\exist.png")
        self.assertEqual(fam, FAMILY_GENERAL)
        self.assertEqual(source, "meta")

    def test_unknown_without_image_defaults_general(self):
        fam, source = resolve_family_with_fallback("", None)
        self.assertEqual(fam, FAMILY_GENERAL)
        self.assertEqual(source, "default")

    def test_unknown_with_bad_image_vl_fallback_fails_safe(self):
        fam, source = resolve_family_with_fallback("占星术", "Z:\\not\\exist.png")
        self.assertEqual(fam, FAMILY_GENERAL)
        self.assertEqual(source, "vl")


if __name__ == "__main__":
    unittest.main()
