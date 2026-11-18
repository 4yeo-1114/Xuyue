# -*- mode: python ; coding: utf-8 -*-
import os
import shutil
import sysconfig

# 前端构建产物目录：优先读 FRONTEND_DIST 环境变量（build_exe.sh 支持覆盖），缺省兜底原路径
FRONTEND_DIST = os.environ.get(
    "FRONTEND_DIST",
    r"F:\education666\job_贺凡\job2\叙阅\grade-buddy-scan-main\dist",
)

# pywin32 胶水 DLL 落到 _internal 根：frozen exe 不会把 pywin32_system32/ 加进 Windows
# DLL 搜索路径，win32print/win32ui 导入会因找不到 pywintypes312.dll 而失败
# （表象=「仅支持 Windows，请安装 pywin32」）。放到 exe 同级目录即可被搜到。
# 坑：PyInstaller 按源文件去重，pywin32 hook 收的 pywin32_system32/ 条目会把 datas 里
# 同源的根目录条目挤掉（Analysis 两条都在、COLLECT 只剩 hook 那条）——所以先把两个 DLL
# 复制到独立源目录 win32glue/ 再喂 datas，源不同就不会被去重打掉。
_SITE_PACKAGES = sysconfig.get_paths()["purelib"]
_GLUE_SRC_DIR = os.path.join(SPECPATH, "win32glue")
os.makedirs(_GLUE_SRC_DIR, exist_ok=True)
for _dll in ("pywintypes312.dll", "pythoncom312.dll"):
    shutil.copy2(
        os.path.join(_SITE_PACKAGES, "pywin32_system32", _dll),
        os.path.join(_GLUE_SRC_DIR, _dll),
    )
_GLUE_DLLS = [
    (os.path.join(_GLUE_SRC_DIR, "pywintypes312.dll"), "."),
    (os.path.join(_GLUE_SRC_DIR, "pythoncom312.dll"), "."),
    (os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "mfc140u.dll"), "."),
]


a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[(FRONTEND_DIST, 'frontend')] + _GLUE_DLLS,
    hiddenimports=['uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'uvicorn.lifespan.off', 'sqlalchemy.ext.baked', 'win32print', 'win32ui', 'win32con', 'win32api', 'pywintypes', 'win32com', 'win32com.client', 'pythoncom'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['IPython', 'jupyter', 'jupyterlab', 'notebook', 'nbformat', 'jupyter_client', 'jupyter_core', 'jedi', 'parso', 'black', 'yapf', 'mypy', 'pytest', 'scipy', 'seaborn', 'sklearn', 'scikit_learn', 'tensorflow', 'torch', 'torchvision', 'keras', 'boto3', 'botocore', 's3transfer', 'zmq', 'pyzmq', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'wx', 'wmi', 'numexpr', 'bottleneck', 'dask', 'distributed', 'h5py', 'fastparquet', 'pyarrow', 'bokeh', 'selenium', 'astropy', 'django', 'playwright', 'lz4', 'xyzservices', 'imageio', 'imageio_ffmpeg', 'av', 'cv2', 'skimage', 'scikit_image', 'joblib', 'threadpoolctl', 'tables', 'zstandard', 'snappy', 'paramiko', 'celery', 'redis', 'kombu', 'tornado', 'prompt_toolkit', 'nbconvert', 'mistune', 'ipykernel', 'qtconsole'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='叙阅',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='叙阅',
)
