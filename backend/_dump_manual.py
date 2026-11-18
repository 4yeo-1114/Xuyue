# -*- coding: utf-8 -*-
"""只读导出：本地安装包 grading_data_all 里的 manual_analyze 块 + 标准答案。"""
import json
import sys
from pathlib import Path

ROOTS = [
    Path(r"D:\叙阅本地化安装包_20261116\app\grading_data_all"),
    Path(r"D:\叙阅源码包_20261115\叙阅迁移包_20260920\backend\grading_data_all"),
]


def main() -> int:
    files = []
    for root in ROOTS:
        if root.is_dir():
            files.extend(root.rglob("*__manual.json"))
            files.extend(root.rglob("*.json"))
    files = sorted(set(files))
    print(f"扫描到 {len(files)} 个 json 文件")

    hit = 0
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        completed = data.get("completed")
        if not isinstance(completed, dict):
            continue
        items = []
        for name, item in completed.items():
            try:
                inner = json.loads((item or {}).get("result") or "{}")
            except Exception:
                continue
            if isinstance(inner, dict) and inner.get("type") == "manual_analyze":
                items.append((name, inner))
        if not items:
            continue
        hit += 1
        ak = data.get("answer_key") or {}
        print("\n" + "=" * 70)
        print("FILE:", path)
        print("标准答案 answers:", json.dumps(ak.get("answers") or {}, ensure_ascii=False))
        print("标准答案 raw:", (str(ak.get("raw") or ""))[:400])
        for name, inner in items[:3]:
            blocks = inner.get("blocks") or []
            print(f"\n--- {name}  块数={len(blocks)}  decisions={len(inner.get('decisions') or {})} ---")
            for b in blocks:
                print(json.dumps({
                    "index": b.get("index"),
                    "sub": b.get("sub_index"),
                    "label": b.get("label"),
                    "kind": b.get("kind"),
                    "status": b.get("status"),
                    "result": b.get("result"),
                    "expected": b.get("expected_answer"),
                    "student": b.get("student_answer"),
                    "bbox": b.get("bbox"),
                    "max_score": b.get("max_score"),
                }, ensure_ascii=False))
    print(f"\n共 {hit} 个文件含 manual_analyze")
    return 0


if __name__ == "__main__":
    sys.exit(main())
