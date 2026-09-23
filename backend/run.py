"""在项目根目录直接运行: python run.py 即可启动后端（等价于运行 app/main.py）"""
import os
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent

if getattr(sys, "frozen", False) and (sys.stdout is None or sys.stderr is None):
    _log_dir = Path(sys.executable).resolve().parent / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _log_file = open(_log_dir / "app.log", "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = _log_file
    if sys.stderr is None:
        sys.stderr = _log_file

# 先检查依赖是否已安装（当前使用的 Python 解释器下）
try:
    import sqlalchemy  # noqa: F401
except ModuleNotFoundError:
    print("当前 Python 环境缺少后端依赖，请先执行：")
    print(f"  {sys.executable} -m pip install -r {_root / 'requirements.txt'}")
    print("然后再重新运行 run.py")
    sys.exit(1)

# 保证从任意工作目录运行都能找到 app 包
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import uvicorn
from app.main import app

_URL = "http://127.0.0.1:6888"


def _run_uvicorn_blocking() -> None:
    uvicorn.run(app, host="127.0.0.1", port=6888, reload=False)


if __name__ == "__main__":
    # 打包后：若服务已在运行（例如用户关了浏览器又点 exe），只打开浏览器不重复起服务
    if getattr(sys, "frozen", False):
        import socket
        import webbrowser

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(("127.0.0.1", 6888))
            s.close()
            if os.environ.get("GRADE_BUDDY_NO_BROWSER") != "1":
                webbrowser.open(_URL)
            sys.exit(0)
        except (socket.error, OSError):
            pass
        # 首启：直接启动服务，不再显示额外控制弹窗。
        # 浏览器自动打开由 app.main 的 lifespan 处理（避免重复打开多个标签页）。
        _run_uvicorn_blocking()
    else:
        # 本地开发：reload=True 让改代码后自动重启，不用每次手动重启后端
        # 注意：reload 必须传导入字符串（而非对象）才能自动重载
        uvicorn.run("app.main:app", host="127.0.0.1", port=6888, reload=True)
