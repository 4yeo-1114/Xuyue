# -*- coding: utf-8 -*-
"""数据漫游：班级考试数据的 zip 打包导出 / 解包还原导入。

导出  GET  /api/v1/grading/folders/export?class_id={id}
导入  POST /api/v1/grading/folders/import   (multipart/form-data: file + class_id)

zip 内部镜像数据根目录相对路径（含 cls_{class_id}__{exam}/ 前缀），导入端负责前缀重写。
数据根目录布局见 app/grading/user_paths.UserGradingPaths：
  correct_documents/test_paper/       -> zip test_paper/
  correct_documents/test_paper_img/   -> zip test_paper_img/
  grading_history/{safe}.json 等      -> zip grading_history/
  modify/                             -> zip modify/
  ct/cls_{class_id}/                  -> zip ct/cls_{class_id}/
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.dependencies import bind_grading_user_context
from app.grading.user_paths import (
    correct_docs_dir,
    correct_docs_img_dir,
    ct_root,
    grading_history_dir,
    modify_dir,
)

router = APIRouter(
    prefix="/grading",
    tags=["grading-data-export"],
    dependencies=[Depends(bind_grading_user_context)],
)

_IMG_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp")
_HISTORY_SUFFIXES = (".json", "__manual.json", "__essay.json")


# ---------- 通用小工具 ----------

def _safe_class_token(class_id: Optional[str]) -> str:
    s = str(class_id or "").strip()
    if not s:
        return ""
    token = "".join(c for c in s if c.isalnum() or c in ("-", "_"))
    return token[:64]


def _split_class_exam(folder_safe: str) -> tuple[str, str]:
    """从 cls_<class_id>__<exam_name> 文件夹名中拆出 class token 与考试名。"""
    safe = str(folder_safe or "").strip()
    if not safe.startswith("cls_") or "__" not in safe:
        return "", safe
    prefix, exam_name = safe.split("__", 1)
    return prefix[4:], exam_name.strip()


def _iter_files(root: Path):
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path


def _history_modify_filenames(text: str) -> set[str]:
    """从 grading_history JSON 文本中收集 modify 目录里被引用的留痕图文件名。

    兼容两种存储形态：完整 URL（/api/v1/grading/modify/xxx.jpg?ticket=...）与裸文件名。
    """
    names: set[str] = set()
    try:
        data = json.loads(text)
    except Exception:
        return names

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)
        elif isinstance(obj, str):
            s = obj
            if "/modify/" in s:
                base = s.split("?", 1)[0].split("#", 1)[0]
                fn = base.rsplit("/", 1)[-1]
                if fn and fn.lower().endswith(_IMG_SUFFIXES):
                    names.add(fn)
            elif not s.startswith("/") and s.lower().endswith(_IMG_SUFFIXES):
                names.add(s)

    walk(data)
    return names


def _collect_folder_modify_names(safe: str) -> list[str]:
    """导出端：收集某个考试文件夹在 modify/ 下的留痕图文件名。"""
    names: set[str] = set()
    for suffix in _HISTORY_SUFFIXES:
        hf = grading_history_dir() / f"{safe}{suffix}"
        if hf.is_file():
            try:
                names.update(_history_modify_filenames(hf.read_text(encoding="utf-8")))
            except Exception:
                pass
    # ref_/manual_ 前缀的留痕图带文件夹名，属该 folder 明确范围
    try:
        for path in modify_dir().iterdir():
            if path.is_file():
                name = path.name
                if f"ref_{safe}_" in name or f"manual_{safe}_" in name:
                    names.add(name)
    except OSError:
        pass
    return sorted(names)


# ---------- 导出 ----------

@router.get("/folders/export")
async def api_export_folders(class_id: Optional[str] = None):
    """导出班级全部考试文件夹为 zip（跨设备数据漫游手动迁移用）。"""
    token = _safe_class_token(class_id)
    if not token:
        raise HTTPException(status_code=404, detail="class_id 不能为空，未找到对应班级数据")
    prefix = f"cls_{token}__"

    docs_root = correct_docs_dir()
    try:
        folder_names = sorted(
            d.name for d in docs_root.iterdir()
            if d.is_dir() and d.name.startswith(prefix)
        )
    except OSError:
        folder_names = []
    if not folder_names:
        raise HTTPException(status_code=404, detail=f"未找到班级 {class_id} 的考试数据，无法导出")

    buf = io.BytesIO()
    seen: set[str] = set()
    manifest_folders: list[dict[str, Any]] = []

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for safe in folder_names:
            exam_name = _split_class_exam(safe)[1] or safe
            files_count = 0

            # 1) 原始试卷 + 标准答案
            src = docs_root / safe
            if src.is_dir():
                for path in _iter_files(src):
                    arc = "test_paper/" + path.relative_to(docs_root).as_posix()
                    if arc not in seen:
                        zf.write(str(path), arc)
                        seen.add(arc)
                        files_count += 1

            # 2) 预览图
            img_root = correct_docs_img_dir()
            img_src = img_root / safe
            if img_src.is_dir():
                for path in _iter_files(img_src):
                    arc = "test_paper_img/" + path.relative_to(img_root).as_posix()
                    if arc not in seen:
                        zf.write(str(path), arc)
                        seen.add(arc)
                        files_count += 1

            # 3) 批改历史 JSON
            for suffix in _HISTORY_SUFFIXES:
                hf = grading_history_dir() / f"{safe}{suffix}"
                if hf.is_file():
                    arc = "grading_history/" + hf.name
                    if arc not in seen:
                        zf.write(str(hf), arc)
                        seen.add(arc)
                        files_count += 1

            # 4) 留痕图（modify/）
            for name in _collect_folder_modify_names(safe):
                arc = "modify/" + name
                if arc in seen:
                    continue
                mp = modify_dir() / name
                if mp.is_file():
                    zf.write(str(mp), arc)
                    seen.add(arc)
                    files_count += 1

            manifest_folders.append({"name": safe, "exam_name": exam_name, "files": files_count})

        # 5) 错题本 ct/cls_{class_id}/
        ct_src = ct_root() / f"cls_{token}"
        if ct_src.is_dir():
            for path in _iter_files(ct_src):
                arc = "ct/" + path.relative_to(ct_root()).as_posix()
                if arc not in seen:
                    zf.write(str(path), arc)
                    seen.add(arc)

        manifest = {
            "version": 1,
            "source_class_id": str(class_id or ""),
            "folders": manifest_folders,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    data = buf.getvalue()
    filename = f"grade_buddy_export_{token}_{datetime.now().strftime('%Y%m%d')}.zip"
    quoted = quote(filename)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )


# ---------- 导入 ----------

def _extract_zip_safely(raw: bytes, extract_root: Path, errors: list[dict[str, str]]) -> None:
    """解包 zip 到 extract_root，zip-slip 穿越条目跳过并记入 errors。"""
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        root_resolved = str(extract_root.resolve())
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or re.match(r"^[a-zA-Z]:", name):
                errors.append({"name": name, "message": "包含绝对路径，已跳过"})
                continue
            parts = name.split("/")
            if any(p == ".." for p in parts):
                errors.append({"name": name, "message": "包含目录穿越路径，已跳过"})
                continue
            target = extract_root.joinpath(*[p for p in parts if p and p != "."]).resolve()
            if not str(target).startswith(root_resolved + os.sep):
                errors.append({"name": name, "message": "路径越界，已跳过"})
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                with zf.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            except Exception as e:  # noqa: BLE001
                errors.append({"name": name, "message": f"解包失败: {e}"})


def _infer_source_folders(extract_root: Path) -> list[str]:
    """从 zip 解包目录推断源考试文件夹名：优先 test_paper/，其次 grading_history/。"""
    folders: list[str] = []
    docs_src = extract_root / "test_paper"
    if docs_src.is_dir():
        for d in sorted(docs_src.iterdir()):
            if d.is_dir() and d.name.startswith("cls_") and "__" in d.name:
                folders.append(d.name)
    if folders:
        return folders

    seen: set[str] = set()
    gh_src = extract_root / "grading_history"
    if gh_src.is_dir():
        for f in sorted(gh_src.iterdir()):
            if not f.is_file():
                continue
            nm = f.name
            for suffix in ("__essay.json", "__manual.json", ".json"):
                if nm.endswith(suffix):
                    base = nm[: -len(suffix)]
                    if base and base not in seen:
                        seen.add(base)
                        folders.append(base)
                    break
    return folders


def _rewrite_folder(old_safe: str, new_token: str) -> str:
    """cls_{old}__{exam} -> cls_{new}__{exam}（new_token 为已 sanitize 的 class_id）。

    非标准名称（无 cls_ 前缀或不含 __）保持原样，不做破坏性改写。
    """
    if old_safe.startswith("cls_") and "__" in old_safe:
        _prefix, exam = old_safe.split("__", 1)
        return f"cls_{new_token}__{exam}"
    return old_safe


def _copy_tree_no_overwrite(src: Path, dst: Path) -> None:
    """合并复制目录树：目标已存在的文件不覆盖。"""
    if not src.is_dir():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for path in src.rglob("*"):
        if path.is_dir():
            continue
        target = dst / path.relative_to(src)
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(str(path), str(target))
        except OSError:
            pass


def _import_ct(extract_root: Path, old_token: Optional[str], new_token: str) -> None:
    """导入错题本 ct/cls_{old} -> ct/cls_{new}（合并不覆盖）。"""
    src_ct = extract_root / "ct"
    if not src_ct.is_dir():
        return
    target_ct = ct_root()
    target_ct.mkdir(parents=True, exist_ok=True)
    if old_token:
        _copy_tree_no_overwrite(src_ct / f"cls_{old_token}", target_ct / f"cls_{new_token}")
    else:
        for d in sorted(src_ct.iterdir()):
            if d.is_dir() and d.name.startswith("cls_"):
                _copy_tree_no_overwrite(d, target_ct / d.name)


@router.post("/folders/import")
async def api_import_folders(
    file: UploadFile = File(...),
    class_id: str = Form(...),
):
    """导入 zip，解包还原班级考试数据到当前登录用户数据根目录。"""
    filename = (file.filename or "").strip().lower()
    if not filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="上传文件必须是 .zip 压缩包")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="上传文件为空")

    try:
        is_zip = zipfile.is_zipfile(io.BytesIO(raw))
    except Exception:
        is_zip = False
    if not is_zip:
        raise HTTPException(status_code=400, detail="上传文件不是有效的 zip 压缩包")

    new_token = _safe_class_token(class_id)
    if not new_token:
        raise HTTPException(status_code=400, detail="class_id 不能为空")

    errors: list[dict[str, str]] = []
    extract_root: Optional[Path] = None
    try:
        extract_root = Path(tempfile.mkdtemp(prefix="grade_buddy_import_"))
        _extract_zip_safely(raw, extract_root, errors)

        # 读取 manifest（缺失时按目录推断）
        manifest: Optional[dict[str, Any]] = None
        manifest_path = extract_root / "manifest.json"
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                manifest = None

        old_token: Optional[str] = None
        if isinstance(manifest, dict):
            src_cid = manifest.get("source_class_id")
            if isinstance(src_cid, str) and src_cid.strip():
                old_token = _safe_class_token(src_cid)

        source_folders = _infer_source_folders(extract_root)
        if not source_folders:
            raise HTTPException(status_code=400, detail="压缩包中未找到任何考试文件夹数据")

        if not old_token:
            for fs in source_folders:
                if fs.startswith("cls_") and "__" in fs:
                    old_token = fs.split("__", 1)[0][4:]
                    break

        docs_src = extract_root / "test_paper"
        img_src_root = extract_root / "test_paper_img"
        gh_src = extract_root / "grading_history"
        modify_src = extract_root / "modify"

        imported: list[str] = []
        skipped: list[dict[str, str]] = []

        for old_safe in source_folders:
            exam_name = _split_class_exam(old_safe)[1] or old_safe
            new_safe = _rewrite_folder(old_safe, new_token)

            # 判重：目标端已存在同名文件夹 -> 跳过，不覆盖不合并
            if (correct_docs_dir() / new_safe).exists():
                skipped.append({"exam_name": exam_name, "reason": "目标端已存在同名文件夹，已跳过"})
                continue

            try:
                # 1) test_paper
                src_docs = docs_src / old_safe
                if src_docs.is_dir():
                    shutil.copytree(str(src_docs), str(correct_docs_dir() / new_safe))
                else:
                    (correct_docs_dir() / new_safe).mkdir(parents=True, exist_ok=True)

                # 2) test_paper_img
                src_img = img_src_root / old_safe
                if src_img.is_dir():
                    shutil.copytree(str(src_img), str(correct_docs_img_dir() / new_safe))

                # 3) grading_history（前缀重写：old_safe -> new_safe）
                for suffix in _HISTORY_SUFFIXES:
                    src_h = gh_src / f"{old_safe}{suffix}"
                    if src_h.is_file():
                        text = src_h.read_text(encoding="utf-8")
                        if old_safe != new_safe:
                            text = text.replace(old_safe, new_safe)
                        dest_h = grading_history_dir() / f"{new_safe}{suffix}"
                        dest_h.parent.mkdir(parents=True, exist_ok=True)
                        dest_h.write_text(text, encoding="utf-8")

                # 4) modify 留痕图（按 history 引用 + ref_/manual_ 前缀收集）
                modify_names: set[str] = set()
                for suffix in _HISTORY_SUFFIXES:
                    src_h = gh_src / f"{old_safe}{suffix}"
                    if src_h.is_file():
                        try:
                            modify_names.update(_history_modify_filenames(src_h.read_text(encoding="utf-8")))
                        except Exception:
                            pass
                if modify_src.is_dir():
                    for p in modify_src.iterdir():
                        if p.is_file():
                            nm = p.name
                            if f"ref_{old_safe}_" in nm or f"manual_{old_safe}_" in nm:
                                modify_names.add(nm)
                for name in sorted(modify_names):
                    src_m = modify_src / name
                    if not src_m.is_file():
                        continue
                    new_name = name.replace(old_safe, new_safe) if old_safe != new_safe else name
                    dest_m = modify_dir() / new_name
                    if dest_m.exists():
                        continue  # 已存在同名留痕图，不覆盖
                    dest_m.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(str(src_m), str(dest_m))

                imported.append(exam_name)
            except Exception as e:  # noqa: BLE001
                errors.append({"name": exam_name, "message": f"导入失败: {e}"})

        # 5) 错题本 ct/（整班合并复制，不覆盖）
        try:
            _import_ct(extract_root, old_token, new_token)
        except Exception as e:  # noqa: BLE001
            errors.append({"name": "ct", "message": f"错题本导入失败: {e}"})

        return {"ok": True, "imported": imported, "skipped": skipped, "errors": errors}
    finally:
        if extract_root is not None:
            try:
                shutil.rmtree(extract_root, ignore_errors=True)
            except Exception:
                pass
