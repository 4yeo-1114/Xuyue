"""P0 资产引擎只读数据库层（家长端 PG 资产库，双库共存融合）。

- assets_base：全新 declarative_base()，绝不复用 app.database.Base（防资产表被
  init_db → sync_database_schema → Base.metadata.create_all 误建进 MySQL）。
- assets_engine / assets_session：仅当 settings.ASSETS_DB_ENABLED 时才创建，
  未配置/不可达时优雅降级，不进 fail-fast。
- get_asset_db()：FastAPI 依赖注入，enabled=False 时直接 503。
- probe_assets_db()：启动 SELECT 1 探活，失败仅告警不阻断（不在模块导入顶层执行）。

风格对齐 app/database.py。
"""
import logging

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

logger = logging.getLogger(__name__)

# 资产模型挂载的独立 metadata（全新 declarative_base）
assets_base = declarative_base()

# 仅当显式开启 ASSETS_DB_ENABLED 时才建立 PG 只读连接池
if settings.ASSETS_DB_ENABLED:
    assets_engine = create_engine(
        settings.assets_database_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=False,
    )
else:
    assets_engine = None

assets_session = sessionmaker(autocommit=False, autoflush=False, bind=assets_engine)


def get_asset_db():
    """FastAPI 依赖注入：yield 资产库只读 session。

    ASSETS_DB_ENABLED=False（未配置）时返回 503，明确告知原因，不静默。
    """
    if not settings.ASSETS_DB_ENABLED or assets_engine is None:
        raise HTTPException(
            status_code=503,
            detail={"enabled": False, "reason": "assets db not configured"},
        )
    db = assets_session()
    try:
        yield db
    finally:
        db.close()


def probe_assets_db() -> bool:
    """启动探活：SELECT 1 验证 PG 资产库连通性。

    - 必须由调用方在启动流程显式调用（不写进模块导入顶层）。
    - 失败仅 logger.warning，不阻断启动；未配置时直接返回 False。
    """
    if not settings.ASSETS_DB_ENABLED or assets_engine is None:
        return False
    try:
        with assets_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("assets db probe ok")
        return True
    except Exception:
        logger.warning("assets db probe failed (will degrade gracefully)", exc_info=True)
        return False
