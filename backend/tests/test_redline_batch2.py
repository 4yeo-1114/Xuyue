# -*- coding: utf-8 -*-
"""B 端红线输出侧过滤挂点补充验收测试（batch 2）。

覆盖 3 个真实 AI 内容生成出口：
  1. targeted_improvement._generate_student_ai — 薄弱点改进建议（批量逐学生，返回结构化 dict）
  2. student_analysis.run_ai_diagnosis        — 错题深度能力诊断（返回 JSON 数组）
  3. class_analysis.generate_analysis         — 班级学情分析（返回结构化 dict）

三个挂点均走 `_filter_redline_deep`（递归深滤所有字符串值，结构保持）：
用 mock LLM / 依赖的方式端到端验证——删除类词条（全脑开发）被删、
替换类词条（窗口期→关键阶段 / 21天养成习惯→习惯养成需要时间）被改写，
且 JSON 结构不被破坏、仍可 json.loads 解析。
"""
import json
from unittest.mock import MagicMock, patch

import pytest


# ── 1. targeted_improvement._generate_student_ai（批量逐学生，一处覆盖所有学生）──

def test_generate_student_ai_filters_redline():
    from app.routers import targeted_improvement as ti

    ai_data = {
        "diagnosis": {
            "summary": "该生需要全脑开发训练，请抓住窗口期",
            "weak_points": ["全脑开发不足"],
        },
        "plan": {"goal": "21天养成习惯", "phases": []},
    }
    with (
        patch.object(ti, "_call_qwen_with_config", return_value=ai_data),
        patch.object(ti, "filter_text", wraps=ti.filter_text) as mock_ft,
    ):
        name, data, err = ti._generate_student_ai("test-key", "qwen", "学生A", "prompt")

    assert err is None
    assert name == "学生A"
    assert mock_ft.called
    raw = json.dumps(data, ensure_ascii=False)
    assert "全脑开发" not in raw           # 删除类命中
    assert "关键阶段" in raw               # 窗口期 → 关键阶段
    assert "习惯养成需要时间" in raw       # 21天养成习惯 → 习惯养成需要时间
    assert isinstance(data, dict)         # 结构保持（仍是 dict）


# ── 2. student_analysis.run_ai_diagnosis（返回 JSON 数组，解析后深滤）───────────

def test_ai_diagnosis_filters_redline_and_keeps_json(tmp_path):
    from app.routers import student_analysis as sa
    from app.schemas.student_analysis import AIDiagnosisRequest

    body = AIDiagnosisRequest(class_id="cls_1", student_name="张三", subject="数学")
    ai_json = json.dumps(
        [
            {
                "dim": "全脑开发训练",
                "student": 85,
                "class": 75,
                "subDims": [{"name": "抓住窗口期", "mastery": 70}],
            }
        ],
        ensure_ascii=False,
    )
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"choices": [{"message": {"content": ai_json}}]}
    (tmp_path / "cls_1_2026.json").write_text("{}", encoding="utf-8")

    def _fake_read(safe, kind):
        if kind == "default":
            return {"completed": {}}
        return {"completed": {"张三_001": {"result": json.dumps({"scores": {"全脑开发训练": 0}})}}}

    diag_file = tmp_path / "diag.json"
    from app.routers import targeted_improvement as ti
    with (
        patch.object(sa, "require_ai_access"),
        patch.object(sa, "assert_no_sensitive_input", return_value=False),
        patch.object(sa, "_assert_class_access"),
        patch.object(sa, "_class_folder_prefix", return_value="cls_1_"),
        patch.object(sa, "grading_history_dir", return_value=tmp_path),
        patch.object(sa, "_read_grading_history", side_effect=_fake_read),
        patch.object(sa, "get_qwen_config", return_value=("test-key", "qwen")),
        patch("requests.post", return_value=fake_resp),
        patch.object(sa, "_get_diagnosis_file", return_value=diag_file),
        patch.object(ti, "filter_text", wraps=ti.filter_text) as mock_ft,
    ):
        result = sa.run_ai_diagnosis(body, user_id="U1", db=None)

    assert mock_ft.called
    raw = json.dumps(result.data, ensure_ascii=False)
    assert "全脑开发" not in raw
    assert "关键阶段" in raw
    # JSON 结构不被破坏：仍是合法数组，键名/嵌套完整，可再次解析
    assert isinstance(result.data, list)
    assert result.data[0]["dim"] == "训练"
    assert result.data[0]["subDims"][0]["name"] == "抓住关键阶段"
    assert json.loads(raw)


# ── 3. class_analysis.generate_analysis（班级学情分析，结构化 dict 深滤）───────

def test_class_analysis_filters_redline():
    from app.routers import class_analysis as ca
    from app.routers.class_analysis import GenerateClassAnalysisRequest

    body = GenerateClassAnalysisRequest(
        class_id="cls_1", subject="数学", exam_folder_names=["cls_1_数学01"]
    )
    raw_analysis = {
        "overall_level": {
            "level": "中",
            "summary": "班级整体需要全脑开发训练，抓住窗口期",
            "trend": "上升",
            "score_interpretation": "分数解读",
            "strengths": ["计算能力扎实"],
            "data_notes": ["数据说明"],
        },
        "knowledge_heatmap": [],
        "weak_points": [],
        "student_warnings": [],
        "teaching_actions": ["加强全脑开发训练"],
    }
    deterministic = {
        "exam_order": [],
        "warning_candidates": [],
        "students": [],
        "class": {"class_name": "一班"},
        "overall_metrics": {},
        "exam_summaries": [],
    }

    from app.routers import targeted_improvement as ti
    with (
        patch.object(ca, "require_ai_access"),
        patch.object(ca, "_assert_class_access"),
        patch.object(ca, "_class_folder_prefix", return_value="cls_1_"),
        patch.object(ca, "_build_analysis_payload", return_value=(deterministic, [], [])),
        patch.object(ca, "get_qwen_config", return_value=("test-key", "qwen")),
        patch.object(ca, "_qwen_completion", return_value=raw_analysis),
        patch.object(ca, "_upsert_db_report", return_value=MagicMock()),
        patch.object(ca, "_db_report_to_dict", return_value=None),
        patch.object(ca, "_write_file_report"),
        patch.object(ti, "filter_text", wraps=ti.filter_text) as mock_ft,
    ):
        result = ca.generate_analysis(body, user_id="U1", db=MagicMock())

    assert mock_ft.called
    raw = json.dumps(result.data, ensure_ascii=False)
    assert "全脑开发" not in raw
    assert "关键阶段" in raw
    report_analysis = result.data["report"]["analysis"]
    assert isinstance(report_analysis["teaching_actions"], list)
    assert json.loads(raw)
