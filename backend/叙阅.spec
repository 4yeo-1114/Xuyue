# -*- mode: python ; coding: utf-8 -*-
import os

# 前端构建产物目录：优先读 FRONTEND_DIST 环境变量（build_exe.sh 支持覆盖），缺省兜底原路径
FRONTEND_DIST = os.environ.get(
    "FRONTEND_DIST",
    r"F:\education666\job_贺凡\job2\叙阅\grade-buddy-scan-main\dist",
)


a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[(FRONTEND_DIST, 'frontend')],
    hiddenimports=['uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'uvicorn.lifespan.off', 'sqlalchemy.ext.baked', 'win32print', 'win32ui', 'win32con', 'win32api', 'pywintypes', 'win32com', 'win32com.client', 'pythoncom'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['IPython', 'jupyter', 'jupyterlab', 'notebook', 'nbformat', 'jupyter_client', 'jupyter_core', 'jedi', 'parso', 'black', 'yapf', 'mypy', 'pytest', 'matplotlib', 'scipy', 'seaborn', 'sklearn', 'scikit_learn', 'tensorflow', 'torch', 'torchvision', 'keras', 'boto3', 'botocore', 's3transfer', 'lxml', 'zmq', 'pyzmq', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'wx', 'wmi', 'numexpr', 'bottleneck', 'dask', 'distributed', 'h5py', 'fastparquet', 'pyarrow', 'bokeh', 'selenium', 'astropy', 'django', 'playwright', 'lz4', 'xyzservices', 'imageio', 'imageio_ffmpeg', 'av', 'cv2', 'skimage', 'scikit_image', 'joblib', 'threadpoolctl', 'tables', 'zstandard', 'snappy', 'paramiko', 'celery', 'redis', 'kombu', 'tornado', 'prompt_toolkit', 'nbconvert', 'mistune', 'ipykernel', 'qtconsole'],
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
