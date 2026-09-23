"""运行方式建议：在项目根目录执行 uvicorn app.main:app --reload --port 6888
若用 IDE 或 python app/main.py 直接运行本文件，下面会先把项目根加入路径。"""
import asyncio
import os
import sys
from pathlib import Path
import tempfile

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# 修改系统默认的临时文件目录，避免 C 盘空间不足导致上传大文件(视频等)失败
_temp_dir = _root / "temp"
_temp_dir.mkdir(exist_ok=True)
tempfile.tempdir = str(_temp_dir)

# ── 让 requests 忽略系统代理 ────────────────────────────────────────────
# 后端对外只访问国内服务（文本大模型网关、DashScope、百度 OCR），本来就不该走代理。
# 开发机上若开着 Clash / Mihomo 之类的代理软件（常见端口 7897），requests 会把请求
# 交给它，然后被中途掐断 —— 表现为 ConnectionAbortedError / WinError 10053，
# 上层只能笼统报「AI 解析失败」，很难查。这里统一绕过，生产服务器上无代理，无副作用。
for _proxy_key in (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
):
    os.environ.pop(_proxy_key, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from datetime import datetime
from app.config import settings
from app.database import SessionLocal, init_db
from app.routers import auth, classes, students, admin, system_settings, lesson_plans
from app.routers import textbook_catalogs
from app.routers import todos
from app.routers import canteen
from app.grading.router import router as grading_router, file_router as grading_file_router
from app.grading.data_export import router as grading_data_export_router
from app.grading.scan_trigger import router as grading_scan_router
from app.grading.file_auth import user_id_from_request
from app.grading.user_paths import ensure_user_grading_layout, get_user_grading_paths, migrate_legacy_grading_dirs_if_needed, set_grading_user_id, shared_zyk_dir
from app.utils.security import decode_access_token


def _get_frontend_dir():
    """打包后前端在 _MEIPASS/frontend，开发时为空（不挂载）。"""
    if getattr(sys, "frozen", False):
        p = Path(sys._MEIPASS) / "frontend"
        if p.exists():
            return p
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    migrate_legacy_grading_dirs_if_needed()
    task = None
    if bool(getattr(settings, "AUTO_TODO_NOTIFY_ENABLED", False)):
        async def _loop():
            from app.routers.todos import get_next_pending_remind_at, run_due_notification_job
            app.state.todo_wakeup = asyncio.Event()
            max_sleep = int(getattr(settings, "AUTO_TODO_NOTIFY_INTERVAL_SECONDS", 30) or 30)
            max_sleep = max(1, max_sleep)

            while True:
                db = SessionLocal()
                try:
                    now = datetime.utcnow()
                    run_due_notification_job(db=db, now=now, limit=50)
                    next_at = get_next_pending_remind_at(db=db, after=now)
                except Exception:
                    next_at = None
                finally:
                    db.close()

                sleep_seconds = float(max_sleep)
                if next_at is not None:
                    delta = (next_at - now).total_seconds()
                    if delta <= 0:
                        sleep_seconds = 0.0
                    else:
                        sleep_seconds = min(float(max_sleep), float(delta))

                wake = getattr(app.state, "todo_wakeup", None)
                if wake is None or sleep_seconds <= 0:
                    await asyncio.sleep(0)
                    continue

                wake.clear()
                try:
                    await asyncio.wait_for(wake.wait(), timeout=sleep_seconds)
                except asyncio.TimeoutError:
                    pass

        task = asyncio.create_task(_loop())
    # 打包成 exe 时：启动后自动打开默认浏览器，无需用户手动输入地址
    if getattr(sys, "frozen", False) and os.environ.get("GRADE_BUDDY_NO_BROWSER") != "1":
        import threading
        import webbrowser
        def _open_browser():
            import time
            time.sleep(1.5)
            webbrowser.open("http://127.0.0.1:6888")
        threading.Thread(target=_open_browser, daemon=True).start()
    yield
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Grade Buddy Scan API", lifespan=lifespan)
# 开发环境：允许本地任意端口的前端（localhost / 127.0.0.1）
# H3：CORS 严格白名单（由 ALLOWED_CORS_ORIGINS 环境变量注入，逗号分隔；未配置时回退本地开发白名单）。
# 去掉 allow_origin_regex 任意源正则，禁止带凭据的跨域请求打到任意站点。
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.middleware("http")
async def grading_user_context_middleware(request: Request, call_next):
    """在 async 请求链路中尽早绑定 grading 用户上下文（contextvar 在 async 路由里不会随 Depends 传递）。

    R2 租户上下文：JWT 解出的 user_id 额外写入 request.state.user_id，供后续中间件/路由读取
    （school 归属在 user_roles 动态变更，不注入 JWT claim、不新增 X-School 头）。
    """
    # H2：仅从 Authorization Header 解析身份；不再接受 URL query 里的 access_token。
    token = None
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    if token:
        user_id = decode_access_token(token)
        if user_id:
            request.state.user_id = user_id
            ensure_user_grading_layout(user_id)
            set_grading_user_id(user_id)
    return await call_next(request)


app.include_router(auth.router, prefix="/api/v1")
app.include_router(classes.router, prefix="/api/v1")
app.include_router(students.router, prefix="/api/v1")
app.include_router(grading_router, prefix="/api/v1")
app.include_router(grading_file_router, prefix="/api/v1")
app.include_router(grading_data_export_router, prefix="/api/v1")
app.include_router(grading_scan_router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")

# ── 流水阅卷 / 集体阅卷（管理端 + 老师端 + 共享文件服务）────
from app.routers import admin_flow_grading
app.include_router(admin_flow_grading.router, prefix="/api/v1")

from app.grading.flow_grading import router as flow_grading_router, file_router as flow_file_router
app.include_router(flow_grading_router, prefix="/api/v1")
app.include_router(flow_file_router, prefix="/api/v1")

from app.routers import admin_grading_stats
app.include_router(admin_grading_stats.router, prefix="/api/v1")

from app.routers import admin_dashboard
app.include_router(admin_dashboard.router, prefix="/api/v1")

from app.routers import admin_academic
app.include_router(admin_academic.router, prefix="/api/v1")

app.include_router(system_settings.router, prefix="/api/v1")
app.include_router(todos.router, prefix="/api/v1")
app.include_router(lesson_plans.router, prefix="/api/v1")
app.include_router(textbook_catalogs.router, prefix="/api/v1")
app.include_router(canteen.router, prefix="/api/v1")

from app.routers import exams
app.include_router(exams.router, prefix="/api/v1")

from app.routers import exam_templates
app.include_router(exam_templates.router, prefix="/api/v1")

from app.routers import wrong_questions
app.include_router(wrong_questions.router, prefix="/api/v1")

from app.routers import knowledge_data
app.include_router(knowledge_data.router, prefix="/api/v1")

from app.routers import resources
app.include_router(resources.router, prefix="/api/v1")

from app.routers import ai_resources
app.include_router(ai_resources.router, prefix="/api/v1")

from app.routers import prep_plans
app.include_router(prep_plans.router, prefix="/api/v1")

from app.routers import student_analysis
app.include_router(student_analysis.router, prefix="/api/v1")

from app.routers import targeted_improvement
app.include_router(targeted_improvement.router, prefix="/api/v1")

from app.routers import class_review
app.include_router(class_review.router, prefix="/api/v1")

from app.routers import class_analysis
app.include_router(class_analysis.router, prefix="/api/v1")

from app.routers import school_warnings
app.include_router(school_warnings.router, prefix="/api/v1")

from app.routers import school_assets
app.include_router(school_assets.router, prefix="/api/v1")

# ── R6b contextual bandit 错题推荐（arm=同 kp 变式题 + 降级链）──
from app.routers import bandit_recommend
app.include_router(bandit_recommend.router, prefix="/api/v1")

# ── R3 身份统一：identity_link 桥表只读接入（家长端 PG 桥表，主平台只读）──
from app.routers import identity_link
app.include_router(identity_link.router, prefix="/api/v1")

# ── 家长端只读接口桥：暴露学校学生成绩数据（只读，无 PII 扩展）──
from app.routers import school_bridge
app.include_router(school_bridge.router, prefix="/api/v1")

from app.routers import ai_chat
app.include_router(ai_chat.router, prefix="/api/v1")

from app.routers import ai_chat_history
app.include_router(ai_chat_history.router, prefix="/api/v1")

from app.routers import ai_auto_report
app.include_router(ai_auto_report.router, prefix="/api/v1")

from app.routers import system as system_router
app.include_router(system_router.router, prefix="/api/v1")

# ── E08 学校级 AI 管控：AI 功能开关 ──────────────────────
from app.routers import feature_flags
app.include_router(feature_flags.router, prefix="/api/v1")

from app.routers import multi_project
app.include_router(multi_project.router, prefix="/api/v1")

# ── 种春风三域（A 画像 / B 测评 / C 运营）挂载 ──────────────────────
from app.routers import portfolio
app.include_router(portfolio.router, prefix="/api/v1")

from app.routers.assessment import router as assessment_router, parent_router as parent_router
app.include_router(assessment_router, prefix="/api/v1")
app.include_router(parent_router, prefix="/api/v1")

from app.routers import student_ops
app.include_router(student_ops.router, prefix="/api/v1")

from app.routers import audio
app.include_router(audio.router, prefix="/api/v1")

from app.routers import portfolio_archive
app.include_router(portfolio_archive.router, prefix="/api/v1")

# ── E03/E14 合规后台：行权 + 审计 ──────────────────────────
from app.routers import admin_rights
app.include_router(admin_rights.router, prefix="/api/v1")

from app.routers import admin_audit
app.include_router(admin_audit.router, prefix="/api/v1")

# ── R6c 薄弱点闭环组卷（智能组卷，P2-2 融合）────────────────────────
from app.routers import paper_composer
app.include_router(paper_composer.router, prefix="/api/v1")

# ── 扫描计费统计（扫描消耗 & 用量汇总，类比七牛云计费页）───────────────
from app.routers import scan_billing
app.include_router(scan_billing.router, prefix="/api/v1")

# ── 小程序打印队列（布置作业 → 生成作业纸 → 本机打印代理拉取打印）────────
from app.routers import print_jobs
app.include_router(print_jobs.router, prefix="/api/v1")

# ── 钉钉免登（authCode 换 userid → 匹配叙阅账号 → 发自己的 JWT）────────
from app.dingtalk import router as dingtalk_router
app.include_router(dingtalk_router, prefix="/api/v1")

# ── 钉钉通讯录同步（部门→班级、成员→学生）────────────────────────────
from app.routers import dingtalk_sync
app.include_router(dingtalk_sync.router, prefix="/api/v1")


def _safe_user_file(base: Path, filename: str) -> Path:
    file_path = (base / filename).resolve()
    if not file_path.is_relative_to(base.resolve()):
        raise HTTPException(status_code=403, detail="无效路径")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return file_path


@app.get("/api/v1/grading/modify/{filename:path}")
async def serve_grading_modify(filename: str, request: Request):
    # H2: resource 绑定为 grading/modify/{filename}，下载票须匹配
    user_id = user_id_from_request(request, resource=f"grading/modify/{filename}")
    paths = get_user_grading_paths(user_id)
    return FileResponse(str(_safe_user_file(paths.modify, filename)))


@app.get("/api/v1/grading/home_img/{filename:path}")
async def serve_grading_home_img(filename: str, request: Request):
    # H2: resource 绑定为 grading/home_img/{filename}
    user_id = user_id_from_request(request, resource=f"grading/home_img/{filename}")
    paths = get_user_grading_paths(user_id)
    return FileResponse(str(_safe_user_file(paths.home_img, filename)))


@app.get("/api/v1/zyk_data/{path:path}")
async def serve_zyk_data(path: str, request: Request):
    # H2: resource 绑定为 zyk_data/{path}；资源库是全局共享目录，所有用户同源
    user_id_from_request(request, resource=f"zyk_data/{path}")
    return FileResponse(str(_safe_user_file(shared_zyk_dir(), path)))


@app.get("/api/v1/ct/{path:path}")
async def serve_ct_data(path: str, request: Request):
    # H2: resource 绑定为 ct/{path}
    user_id = user_id_from_request(request, resource=f"ct/{path}")
    paths = get_user_grading_paths(user_id)
    return FileResponse(str(_safe_user_file(paths.ct, path)))



@app.post("/api/v1/system/exit")
async def api_system_exit(request: Request):
    """
    打包 exe 的退出接口：仅允许本机回环地址调用，调用后短延时退出进程。
    前端用于「退出叙阅」按钮。
    """
    client_host = (request.client.host or "") if request.client else ""
    if client_host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=403, detail="仅允许本机调用")
    if not getattr(sys, "frozen", False):
        raise HTTPException(status_code=400, detail="仅打包版支持退出程序")

    import threading
    import time
    import os

    def _exit_later() -> None:
        time.sleep(0.25)
        os._exit(0)

    threading.Thread(target=_exit_later, daemon=True).start()
    return {"ok": True, "msg": "程序即将退出"}


# 打包后处理前端 SPA 路由
_frontend_dir = _get_frontend_dir()
if _frontend_dir is not None:
    from fastapi.staticfiles import StaticFiles

    # 优先挂载静态资源子目录（如 assets），StaticFiles 处理这类路径效率更高
    _assets_path = _frontend_dir / "assets"
    if _assets_path.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets_path)), name="assets")

    # 兜底路由：处理根目录文件（favicon.ico 等）或返回 index.html 实现 SPA 路由
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path:
            file_path = _frontend_dir / full_path
            if file_path.is_file():
                return FileResponse(file_path)

        # 否则返回 index.html，由前端路由（SPA）接管
        index_path = _frontend_dir / "index.html"
        if index_path.exists():
            return FileResponse(index_path)

        raise HTTPException(status_code=404)
else:
    @app.get("/")
    def root():
        return {"message": "Grade Buddy Scan Backend", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    # 直接传 app 对象，避免 uvicorn 再次导入导致路径问题
    # L2: 默认仅监听本机回环地址；如需对外监听，通过 env HOST=0.0.0.0 显式开启
    uvicorn.run(app, host=getattr(settings, "HOST", "127.0.0.1"), port=6888, reload=False)
