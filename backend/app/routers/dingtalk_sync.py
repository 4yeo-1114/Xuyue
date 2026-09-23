# -*- coding: utf-8 -*-
"""钉钉通讯录同步：部门→班级、部门成员→学生（手机号当学号）。

三个接口：
  GET  /dingtalk/status       钉钉是否已配置 + 已同步的班级/学生数
  GET  /dingtalk/departments  拉取全公司部门（前端选择器用）
  POST /dingtalk/sync         选定一个部门（含其子部门）→ 同步成班级+学生
"""
from typing import Any, Dict, List

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.class_model import Class
from app.models.student import Student
from app.schemas.common import ApiResponse
from app.dingtalk import _ding_token, _DING_BASE

router = APIRouter(prefix="/dingtalk", tags=["dingtalk-sync"])

DEPT_ROOT = 1  # 钉钉根部门 ID 恒为 1
_VALID_LEVELS = {"primary", "junior", "senior"}


def _ding_post(path: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """带 access_token 调用钉钉 openapi，统一异常处理。"""
    try:
        r = requests.post(
            f"{_DING_BASE}{path}",
            params={"access_token": _ding_token()},
            json=body,
            timeout=15,
        ).json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"调用钉钉失败：{e}")
    if r.get("errcode") != 0:
        raise HTTPException(
            status_code=502,
            detail=f"钉钉通讯录接口失败 {r.get('errcode')}: {r.get('errmsg')}",
        )
    return r


def _list_sub_departments(dept_id: int) -> List[Dict[str, Any]]:
    """某部门的直接子部门列表。"""
    r = _ding_post("/topapi/v2/department/listsub", {"dept_id": dept_id})
    result = r.get("result")
    if isinstance(result, dict):
        return list(result.get("list") or [])
    return list(result or [])


def _list_all_departments() -> List[Dict[str, Any]]:
    """BFS 拉取全公司部门（不含根部门），供前端选择器使用。"""
    out: List[Dict[str, Any]] = []
    queue = [DEPT_ROOT]
    while queue:
        cur = queue.pop(0)
        for sub in _list_sub_departments(cur):
            did = sub.get("dept_id")
            if did is None or int(did) == DEPT_ROOT:
                continue
            out.append(
                {
                    "dept_id": int(did),
                    "name": sub.get("name") or f"部门{did}",
                    "parent_id": sub.get("parent_id"),
                }
            )
            queue.append(int(did))
    return out


def _list_dept_users(dept_id: int) -> List[Dict[str, Any]]:
    """某部门成员（userid+name），自动翻页。"""
    items: List[Dict[str, Any]] = []
    cursor = 0
    while True:
        r = _ding_post(
            "/topapi/v2/user/list",
            {"dept_id": dept_id, "cursor": cursor, "size": 100, "language": "zh_CN"},
        )
        result = r.get("result") or {}
        items.extend(result.get("list") or [])
        if result.get("has_more"):
            cursor = int(result.get("next_cursor") or 0)
            continue
        break
    return items


def _get_user_detail(userid: str) -> Dict[str, Any]:
    """成员详情（含手机号）。"""
    r = _ding_post(
        "/topapi/v2/user/get", {"userid": userid, "language": "zh_CN"}
    )
    return r.get("result") or {}


def _collect_subtree(dept_id: int, all_depts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按 parent_id 关系，收集指定部门及其全部后代。"""
    by_parent: Dict[int, List[Dict[str, Any]]] = {}
    for d in all_depts:
        by_parent.setdefault(d.get("parent_id") or 0, []).append(d)

    selected: List[Dict[str, Any]] = []
    seen = set()
    queue = [dept_id]
    while queue:
        cur = queue.pop(0)
        if cur in seen:
            continue
        seen.add(cur)
        info = next((d for d in all_depts if d["dept_id"] == cur), None)
        if info:
            selected.append(info)
        for sub in by_parent.get(cur, []):
            queue.append(sub["dept_id"])
    return selected


class SyncRequest(BaseModel):
    dept_id: int
    school_level: str  # primary / junior / senior
    grade: str


@router.get("/status", response_model=ApiResponse[dict])
def dingtalk_status(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    configured = bool((settings.DINGTALK_APP_KEY or "").strip()) and bool(
        (settings.DINGTALK_APP_SECRET or "").strip()
    )
    class_count = (
        db.query(Class)
        .filter(Class.dingtalk_dept_id.isnot(None), Class.user_id == user_id)
        .count()
    )
    student_count = (
        db.query(Student)
        .filter(Student.dingtalk_userid.isnot(None), Student.user_id == user_id)
        .count()
    )
    return ApiResponse(
        data={
            "configured": configured,
            "synced_class_count": class_count,
            "synced_student_count": student_count,
        }
    )


@router.get("/departments", response_model=ApiResponse[List[dict]])
def dingtalk_departments(user_id: str = Depends(get_current_user_id)):
    return ApiResponse(data=_list_all_departments())


@router.post("/sync", response_model=ApiResponse[dict])
def dingtalk_sync(
    body: SyncRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    level = (body.school_level or "").strip()
    grade = (body.grade or "").strip()
    if level not in _VALID_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"学段取值应为 primary / junior / senior，收到 {level!r}",
        )
    if not grade:
        raise HTTPException(status_code=400, detail="请填写年级")
    if body.dept_id == DEPT_ROOT:
        raise HTTPException(status_code=400, detail="请选择一个具体部门（不能选根部门）")

    # 1) 收集要同步的部门（选定部门 + 全部后代）
    all_depts = _list_all_departments()
    selected = _collect_subtree(body.dept_id, all_depts)
    if not selected:
        raise HTTPException(status_code=400, detail="该部门下没有可同步的部门")

    class_created = class_updated = 0
    student_created = student_updated = 0
    touched_classes: List[Class] = []

    for dept in selected:
        dept_id = dept["dept_id"]
        dept_name = dept["name"] or f"钉钉部门{dept_id}"

        # 2) 部门 → 班级（按 dingtalk_dept_id 幂等匹配）
        cls = (
            db.query(Class)
            .filter(Class.user_id == user_id, Class.dingtalk_dept_id == str(dept_id))
            .first()
        )
        if cls is None:
            cls = Class(
                user_id=user_id,
                school_level=level,
                grade=grade,
                name=dept_name,
                student_count=0,
                dingtalk_dept_id=str(dept_id),
            )
            db.add(cls)
            db.flush()  # 生成 cls.id，供下面建学生引用
            class_created += 1
        else:
            cls.school_level = level
            cls.grade = grade
            cls.name = dept_name
            class_updated += 1
        touched_classes.append(cls)

        # 3) 成员 → 学生（手机号当学号）
        for m in _list_dept_users(dept_id):
            uid = (m.get("userid") or "").strip()
            if not uid:
                continue
            detail = _get_user_detail(uid)
            name = (detail.get("name") or m.get("name") or "").strip()
            mobile = (detail.get("mobile") or "").strip()

            stu = (
                db.query(Student)
                .filter(Student.class_id == cls.id, Student.dingtalk_userid == uid)
                .first()
            )
            if stu is None and name:
                # 姓名兜底，避免首次同步（或历史数据）重复建同名学生
                stu = (
                    db.query(Student)
                    .filter(
                        Student.class_id == cls.id,
                        Student.name == name,
                        Student.dingtalk_userid.is_(None),
                    )
                    .first()
                )
            if stu is None:
                stu = Student(
                    class_id=cls.id,
                    user_id=cls.user_id,
                    school_id=cls.school_id,
                    name=name or f"钉钉成员{uid}",
                    student_number=mobile or "",
                    phone=mobile or None,
                    dingtalk_userid=uid,
                    tier="B",
                    status="正常",
                )
                db.add(stu)
                student_created += 1
            else:
                if name:
                    stu.name = name
                if mobile:
                    stu.student_number = mobile
                    stu.phone = mobile
                stu.dingtalk_userid = uid
                student_updated += 1

    db.commit()

    # 4) 回填班级学生数
    for cls in touched_classes:
        cls.student_count = (
            db.query(Student).filter(Student.class_id == cls.id).count()
        )
    db.commit()

    # 5) 为新班级建错题目录（与 classes.create_class 保持一致，失败不阻断）
    try:
        from app.grading.wrong_question_db import ensure_class_wrong_question_dir
        from app.grading.user_paths import reset_grading_user_id, set_grading_user_id

        token = set_grading_user_id(user_id)
        try:
            for cls in touched_classes:
                ensure_class_wrong_question_dir(cls.id)
        finally:
            reset_grading_user_id(token)
    except Exception:
        pass

    return ApiResponse(
        data={
            "departments": len(selected),
            "classes_created": class_created,
            "classes_updated": class_updated,
            "students_created": student_created,
            "students_updated": student_updated,
        }
    )
