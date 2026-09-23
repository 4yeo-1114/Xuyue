import sys
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings


def _get_env_file() -> str:
    """开发时读取后端目录 .env；打包后优先读取 exe 同目录 .env，便于部署后改配置。"""
    if getattr(sys, "frozen", False):
        exe_env = Path(sys.executable).resolve().with_name(".env")
        if exe_env.exists():
            return str(exe_env)
        bundled_env = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) / ".env"
        return str(bundled_env)
    return ".env"


class Settings(BaseSettings):
    # 安全修复(C1/C2)：生产凭据不再硬编码默认值，全部改为环境变量/.env 注入。
    # 未配置时启动 fail-fast（见下方 model_validator），绝不带空值或默认弱口令运行。
    DB_HOST: str = ""
    DB_PORT: int = 3306
    DB_USER: str = ""
    DB_PASSWORD: str = ""
    DB_NAME: str = ""
    # 双引擎切换（P3 业务库迁移 F1）：mysql（默认） / postgresql（或别名 pg）
    DB_ENGINE: str = "mysql"

    # JWT（C2）：删除默认弱密钥，必须由环境变量注入；长度 >= 32 才允许启动
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 天

    BAIDU_ACCESS_TOKEN: str = ""
    BAIDU_API_KEY: str = ""
    BAIDU_SECRET_KEY: str = ""
    DASHSCOPE_API_KEY: str = ""
    QWEN_MODEL: str = "qwen3.7-plus"

    # 文本 LLM（OpenAI 兼容网关，可切换供应商，如 DeepSeek 等）。
    # 未配置时回退到 DashScope（向后兼容）；视觉/ASR 仍走 DashScope（qwen-vl-max / qwen3-asr）。
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "qwen3.7-plus"

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USE_SSL: bool = False
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""

    CRON_KEY: str = ""
    AUTO_TODO_NOTIFY_ENABLED: bool = True
    AUTO_TODO_NOTIFY_INTERVAL_SECONDS: int = 30

    # 打印代理令牌：小程序布置作业后，由本机 print_agent.py 凭此令牌来队列取任务。
    # 留空 = 关闭打印功能（代理接口返回 503），不影响其他模块。
    PRINT_AGENT_TOKEN: str = ""

    # C5：生产库禁止启动时自动 DDL（CREATE/ALTER），显式迁移后才打开
    AUTO_DDL: bool = False

    # H5：多项目超级管理员邮箱，逗号分隔；不再硬编码
    MULTI_PROJECT_ADMIN_EMAILS: str = ""

    # H3：CORS 严格白名单，逗号分隔；未配置时回退到本地开发白名单（不含任意源正则）
    ALLOWED_CORS_ORIGINS: str = ""

    # L2：默认仅监听本机回环地址，外网监听需显式配置 HOST=0.0.0.0
    HOST: str = "127.0.0.1"

    # H2：文件直链短时下载票有效期（分钟）
    # 老师常把批改页面一直开着，缩略图懒加载时 ticket 已过期会报 401「未登录」。
    # 之前 10 分钟→2 小时仍不够；这里与登录态 JWT 保持一致（7 天），登录期内图片永不因票过期而失效。
    DOWNLOAD_TICKET_EXPIRE_MINUTES: int = 60 * 24 * 7

    # H4：单用户单日邮件发送上限（防开放邮件转发滥用）
    EMAIL_DAILY_LIMIT: int = 20

    # 钉钉免登：corpId / AppKey / AppSecret / AgentId；留空 = 钉钉免登不可用
    DINGTALK_CORP_ID: str = ""
    DINGTALK_APP_KEY: str = ""
    DINGTALK_APP_SECRET: str = ""
    DINGTALK_AGENT_ID: str = ""
    # 钉钉工作通知：前端公网 base（报告链接跳转用），如 https://foil.6108.net
    DINGTALK_FRONTEND_BASE_URL: str = ""

    # 演示环境免审核注册开关；生产置 False 关闭自助注册
    ALLOW_PUBLIC_REGISTRATION: bool = True

    # PG 题库资产只读连接（P0 融合第一阶段）：可选配置，未配置/不可达时优雅降级，不进 fail-fast
    ASSETS_DB_ENABLED: bool = False
    ASSETS_DB_HOST: str = ""
    ASSETS_DB_PORT: int = 5432
    ASSETS_DB_USER: str = ""
    ASSETS_DB_PASSWORD: str = ""
    ASSETS_DB_NAME: str = "grade"

    @model_validator(mode="after")
    def _validate_required_config(self):
        missing = []
        if not (self.DB_HOST or "").strip():
            missing.append("DB_HOST")
        if not (self.DB_USER or "").strip():
            missing.append("DB_USER")
        if not (self.DB_PASSWORD or "").strip():
            missing.append("DB_PASSWORD")
        if not (self.DB_NAME or "").strip():
            missing.append("DB_NAME")
        if not (self.JWT_SECRET_KEY or "").strip():
            missing.append("JWT_SECRET_KEY")
        if missing:
            raise ValueError(
                "缺少必要配置: " + ", ".join(missing)
                + "。生产凭据必须通过环境变量/.env 注入，禁止硬编码默认值（安全修复 C1/C2）。"
            )
        if len(str(self.JWT_SECRET_KEY).strip()) < 32:
            raise ValueError(
                "JWT_SECRET_KEY 长度必须 >= 32 字符，请生成强随机密钥后通过环境变量注入。"
            )
        return self

    @property
    def db_engine(self) -> str:
        """数据库引擎规范化：postgresql/pg → postgresql，缺省或其他 → mysql。"""
        engine = (self.DB_ENGINE or "").strip().lower()
        if engine in {"postgresql", "pg"}:
            return "postgresql"
        return "mysql"

    @property
    def database_url(self) -> str:
        driver = (
            "postgresql+psycopg2"
            if self.db_engine == "postgresql"
            else "mysql+pymysql"
        )
        return (
            f"{driver}://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def assets_database_url(self) -> str:
        """PG 题库资产只读连接串（可选配置，未注入凭据时返回空凭据串，主业务不受影响）。"""
        return (
            f"postgresql+psycopg2://{self.ASSETS_DB_USER}:{self.ASSETS_DB_PASSWORD}"
            f"@{self.ASSETS_DB_HOST}:{self.ASSETS_DB_PORT}/{self.ASSETS_DB_NAME}"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        """CORS 白名单：优先取 ALLOWED_CORS_ORIGINS 环境变量，未配置时回退本地开发白名单。"""
        raw = (self.ALLOWED_CORS_ORIGINS or "").strip()
        if raw:
            return [o.strip() for o in raw.split(",") if o.strip()]
        return [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "http://localhost:6889",
            "http://127.0.0.1:6889",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:6888",
            "http://127.0.0.1:6888",
        ]

    @property
    def multi_project_admin_emails(self) -> set[str]:
        """H5：多项目超管邮箱集合（逗号分隔，忽略大小写与空白）。"""
        return {
            e.strip().lower()
            for e in (self.MULTI_PROJECT_ADMIN_EMAILS or "").split(",")
            if e.strip()
        }

    class Config:
        env_file = _get_env_file()
        env_file_encoding = "utf-8"


settings = Settings()
