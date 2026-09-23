#!/usr/bin/env bash
# ============================================================
# 叙阅 Windows 桌面版打包脚本（Git Bash 可执行，幂等可重复跑）
#
# C5 安全修复：打包产物一律使用占位 .env（不含任何真实凭据），
#             真实凭据由部署者在部署机上填写 .env 或通过环境变量注入。
#
# 用法：
#   bash scripts/build_exe.sh
#   FRONTEND_DIST=/path/to/frontend/dist bash scripts/build_exe.sh   # 自定义前端产物路径
#
# 依赖：
#   - /e/anaconda 下的 Python 环境（需已安装 PyInstaller）
#   - 叙阅.spec（与脚本同仓库根目录）
#   - 前端构建产物（默认 F:/education666/job_贺凡/job2/叙阅/grade-buddy-scan-main/dist）
# ============================================================
set -euo pipefail

# 项目根目录（脚本所在目录的上一级），保证从任意目录运行都能定位到仓库根
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# ---------- 前端 dist 前置检查 ----------
# 默认路径与 叙阅.spec 中 datas 的源路径保持一致；可通过环境变量覆盖。
FRONTEND_DIST="${FRONTEND_DIST:-F:/education666/job_贺凡/job2/叙阅/grade-buddy-scan-main/dist}"
if [ ! -d "$FRONTEND_DIST" ] || [ -z "$(ls -A "$FRONTEND_DIST" 2>/dev/null)" ]; then
  echo "[ERROR] 前端构建产物不存在或为空: $FRONTEND_DIST" >&2
  echo "        请先构建前端（cd grade-buddy-scan-main && npm run build），" >&2
  echo "        或通过 FRONTEND_DIST=... 指定前端 dist 路径。" >&2
  exit 1
fi
echo "[INFO] 前端产物已就绪: $FRONTEND_DIST"

# ---------- 打包环境 ----------
# libssl 冲突规避：把 anaconda 的 Library/bin 前置到 PATH（现状打包命令的前提）。
export PATH="/e/anaconda/Library/bin:$PATH"

if ! command -v python >/dev/null 2>&1; then
  echo "[ERROR] 未找到 python，请确认 /e/anaconda 环境存在。" >&2
  exit 1
fi
if ! python -m PyInstaller --version >/dev/null 2>&1; then
  echo "[ERROR] PyInstaller 未安装，请先执行: python -m pip install pyinstaller" >&2
  exit 1
fi

if [ ! -f "叙阅.spec" ]; then
  echo "[ERROR] 未找到 叙阅.spec（打包配置），无法执行 PyInstaller。" >&2
  exit 1
fi

# ---------- 清理旧产物（幂等） ----------
echo "[INFO] 清理旧产物 build/ 与 dist/叙阅/"
rm -rf build
rm -rf dist/叙阅

# ---------- PyInstaller onedir 打包 ----------
echo "[INFO] 开始 PyInstaller 打包（--noconfirm --clean 叙阅.spec）..."
python -m PyInstaller --noconfirm --clean 叙阅.spec

# ---------- 产物处理：占位 .env，杜绝真实凭据 ----------
OUT_DIR="dist/叙阅"
if [ ! -d "$OUT_DIR" ]; then
  echo "[ERROR] 打包产物目录不存在: $OUT_DIR" >&2
  exit 1
fi

# 1) 用根目录 .env.example（占位模板，不含任何真实凭据）替换产物中的 .env
if [ -f ".env.example" ]; then
  cp .env.example "$OUT_DIR/.env"
  echo "[INFO] 已将 $OUT_DIR/.env 替换为占位模板（不含真实凭据）。"
else
  echo "[WARN] 未找到 .env.example，跳过 .env 占位替换！部署前请务必手动放置占位 .env。" >&2
fi

# 2) multi_project_settings.json：删除打包时带入的真实配置，
#    首次启动时 app 会依据部署者填写的 .env/环境变量自动生成单 profile 安全配置。
#    （多项目场景请在部署机手工创建该文件，密码使用 env:VAR_NAME 引用环境变量。）
if [ -f "$OUT_DIR/multi_project_settings.json" ]; then
  rm -f "$OUT_DIR/multi_project_settings.json"
  echo "[INFO] 已移除产物中的 multi_project_settings.json（避免真实 DB 密码随包分发）。"
fi

# 3) 安全断言：产物 .env 的关键敏感字段必须为空/占位，否则中止
if grep -qE '^(DB_PASSWORD|JWT_SECRET_KEY|SMTP_PASSWORD|CRON_KEY|BAIDU_ACCESS_TOKEN)=[^[:space:]]+' "$OUT_DIR/.env"; then
  echo "[ERROR] 产物 $OUT_DIR/.env 仍含非空敏感字段，拒绝交付。请检查 .env.example。" >&2
  exit 1
fi

# ---------- 完成 ----------
echo ""
echo "================================================================"
echo " 打包完成，最终产物：$ROOT_DIR/$OUT_DIR/"
echo "   - 可执行文件：$ROOT_DIR/$OUT_DIR/叙阅.exe"
echo "   - 占位配置：  $ROOT_DIR/$OUT_DIR/.env（须由部署者填写真实值）"
echo "================================================================"
echo " 部署提醒："
echo "   1. 请填写 $OUT_DIR/.env 中的真实凭据，或通过系统环境变量注入；"
echo "   2. multi_project_settings.json 首次启动会自动生成；"
echo "      多项目场景请手工配置，db profile 密码用 env:VAR_NAME 引用环境变量；"
echo "   3. AUTO_DDL=false 时不会自动建表，需按 docs/DEPLOY.md 手动执行 docs/migrations/ 下的 SQL；"
echo "   4. 真实凭据绝不写入版本库（.env / multi_project_settings.json 均已被 .gitignore 忽略）。"
echo "================================================================"
