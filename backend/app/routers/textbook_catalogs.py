"""教材目录查询（R4 备课 MVP）：GET /textbook-catalogs

供前端教案教材级联选择器使用：按 subject 拉取该学科目录节点列表，
可再按 edition / grade 过滤；节点含 level/unit_index/parent_id，前端据此组树
（edition 顶层 → unit 子节点）。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.textbook_catalog import TextbookCatalog
from app.schemas.common import ApiResponse
from app.schemas.textbook_catalogs import (
    TextbookCatalogNode,
    TextbookCatalogOptions,
    TextbookCatalogPair,
)

router = APIRouter(prefix="/textbook-catalogs", tags=["textbook-catalogs"])


@router.get("", response_model=ApiResponse[List[TextbookCatalogNode]])
def list_textbook_catalogs(
    subject: str = Query(..., description="学科（语文/数学/英语…）"),
    edition: Optional[str] = Query(None, description="教材版本（如「人教版」）"),
    grade: Optional[str] = Query(None, description="年级（如「七年级」）"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    query = db.query(TextbookCatalog).filter(TextbookCatalog.subject == (subject or "").strip())
    if edition is not None and edition.strip():
        query = query.filter(TextbookCatalog.edition == edition.strip())
    if grade is not None and grade.strip():
        query = query.filter(TextbookCatalog.grade == grade.strip())
    # 排序：edition 顶层节点（parent_id NULL）在前，其下单元按 unit_index 升序
    rows = query.order_by(
        TextbookCatalog.edition,
        TextbookCatalog.parent_id,
        TextbookCatalog.unit_index,
    ).all()
    return ApiResponse(data=[TextbookCatalogNode.model_validate(r) for r in rows])


@router.get("/options", response_model=ApiResponse[TextbookCatalogOptions])
def list_textbook_catalog_options(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """四维定位矩阵数据同步：返回教材目录表中实际存在的版本/学科/年级组合。

    前端据此把「四维定位矩阵」从硬编码改为按真实目录数据点亮单元格，
    仅对有目录内容的单元格开放点击跳转（避免点击后落到空目录页）。
    """
    rows = (
        db.query(
            TextbookCatalog.subject,
            TextbookCatalog.grade,
            TextbookCatalog.edition,
            func.count(TextbookCatalog.id),
        )
        .group_by(
            TextbookCatalog.subject,
            TextbookCatalog.grade,
            TextbookCatalog.edition,
        )
        .all()
    )

    pairs = [
        TextbookCatalogPair(
            subject=(subject or ""),
            grade=grade,
            edition=edition,
            node_count=int(count or 0),
        )
        for subject, grade, edition, count in rows
        if (subject or "").strip()
    ]

    editions = sorted({p.edition for p in pairs if p.edition})
    subjects = sorted({p.subject for p in pairs})
    grades = sorted({p.grade for p in pairs if p.grade})

    return ApiResponse(
        data=TextbookCatalogOptions(
            editions=editions,
            subjects=subjects,
            grades=grades,
            pairs=pairs,
        )
    )
