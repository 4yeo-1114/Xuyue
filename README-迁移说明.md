# 叙阅（GradeBuddy）换机迁移说明

> 生成日期：2026-09-20　包体：`叙阅迁移包_20260920`
> 适用：从旧电脑换到新电脑，把「叙阅」整套系统（后端 + 前端 + 微信小程序）原样搬过去继续用。

---

## 一、这套系统是什么

| 部分 | 目录 | 说明 |
|------|------|------|
| 后端 | `backend/` | FastAPI + Python，端口 **6888**，连云端数据库 |
| 前端 | `frontend/` | React + Vite + TypeScript，端口 **6889**，微信扫码/批改台 |
| 小程序 | `miniprogram/` | 微信小程序源码（家长端），在微信开发者工具里打开 |
| 数据 | `backend/grading_data_all/` | 试卷扫描图片、批改结果、资源库（约 1.2G） |
| 部署文档 | `docs/` | 钉钉接入手把手教程等 |

> **数据库不需要迁移**：数据存在阿里云 RDS（MySQL）上，新电脑只要连同一个库账号就能接着用，换机不影响已批改的历史数据。

---

## 二、新电脑要做的事（按顺序）

### 1. 安装基础环境

- **Python 3.11**（务必 3.11，装 3.12/3.13 会有 numpy/pyarrow 兼容问题）
  - 官网下载：https://www.python.org/downloads/release/python-3119/
  - 安装时勾选 **Add Python to PATH**
- **Node.js 20+**（前端需要）
  - 官网下载：https://nodejs.org/（装 LTS 版即可）
  - 装完命令行里能敲 `node -v`、`npm -v` 即成功
- **微信开发者工具**（如果要跑小程序）
  - https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html

### 2. 解压本包

把 `叙阅迁移包_20260920` 解压到一个固定目录，例如：

```
D:\叙阅\
```

里面就是 `backend/`、`frontend/`、`miniprogram/`、`docs/` 和本说明。

### 3. 恢复配置文件（关键）

配置文件是隐藏的 `.env`，打包时已经带上，但新电脑**务必核对一下**：

- `backend/.env` —— 后端配置（数据库账号、各种密钥）
- `frontend/.env` 和 `frontend/.env.production` —— 前端配置

数据库连接信息（已写进 `.env`，一般不用动）：
- 主机：阿里云 RDS
- 库名：`xuyue`
- 账号：`xuyue`

> 换机后如果后端报「数据库连接失败」，先检查这台新电脑能不能访问外网、`.env` 里的 `DB_HOST` / `DB_PASSWORD` 是否完整。

### 4. 启动后端

```bash
cd D:\叙阅\backend
python -m venv venv
# 用 venv 里的 python（或直接用系统 3.11 的 python）装依赖
venv\Scripts\python.exe -m pip install -r requirements.txt
# 启动
venv\Scripts\python.exe run.py
```

启动成功标志：命令行出现 Uvicorn 在 `127.0.0.1:6888` 监听，浏览器访问 http://127.0.0.1:6888 有响应。

> 若依赖装得慢，可加国内源：`-i https://pypi.tuna.tsinghua.edu.cn/simple`

### 5. 启动前端

```bash
cd D:\叙阅\frontend
npm install
npm run dev
```

启动成功后访问 http://127.0.0.1:6889 ，就是「叙阅」的批改台界面。

> 本项目锁文件同时有 `package-lock.json`（npm）和 `bun.lock`（bun），用 npm 或 bun 都行，二选一即可。

### 6. 跑小程序（可选）

用微信开发者工具「导入项目」，选择目录 `D:\叙阅\miniprogram`，AppID 填你自己的，即可预览家长端。

---

## 三、常见问题

**Q：后端起来了但前端打开是空白/连不上？**
A：确认后端 6888、前端 6889 都在跑；前端连后端的地址在 `frontend/.env` 里，核对 IP/端口。

**Q：换机后历史批改记录还在吗？**
A：在。记录都存云端 RDS 数据库，不随电脑迁移，只要 `.env` 的数据库连接对，历史数据原样可见。

**Q：扫描图片/资源库这些大文件搬了吗？**
A：搬了，都在 `backend/grading_data_all/` 里（约 1.2G）。

**Q：numpy / pyarrow 报错？**
A：多为环境噪声，不影响使用；用 Python 3.11 的 venv 可避免。

---

## 四、端口一览

| 服务 | 端口 | 启动命令 |
|------|------|----------|
| 后端 API | 6888 | `python run.py` |
| 前端 | 6889 | `npm run dev` |

> 若旧电脑还开着，别和新电脑同时连库跑批改，避免冲突。
