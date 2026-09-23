# 叙阅 · Windows 桌面版部署说明

> 适用对象：拿到 `dist/叙阅/` 分发目录、需要在本机或客户机部署后端的部署者。
>
> **安全前提（C5）**：打包产物中的 `.env` 是占位模板，**不含任何真实凭据**。
> 真实凭据只允许在部署机上写入，或通过系统环境变量注入，**绝不进入版本库**。

---

## 1. 分发目录结构

打包完成后，交付给部署者的是整个目录：

```
dist/叙阅/
├── 叙阅.exe            # 主程序（双击或命令行启动）
├── .env                  # 占位配置（必须由部署者填写，见 §2）
├── _internal/            # Python 运行时与依赖
├── frontend/             # 前端静态资源（内嵌）
└── grading_data_all/     # 运行时数据目录
```

- `multi_project_settings.json` **不会**随包分发：首次启动时程序会自动依据 `.env`/环境变量生成单 profile 的安全配置（见 §4）。
- `叙阅.exe` 启动后默认监听 `127.0.0.1:6888`（仅本机），浏览器自动打开前端。

---

## 2. 填写 .env（两种方式，任选其一）

### 方式 A：直接编辑产物目录下的 `.env`

打开 `dist/叙阅/.env`（占位模板），把必填项填成真实值：

| 字段 | 必填 | 说明 |
|------|------|------|
| `DB_HOST` | 是 | MySQL 地址，如阿里云 RDS 内网/外网地址 |
| `DB_USER` | 是 | 数据库账号（建议 DML-only，DDL 走人工审批） |
| `DB_PASSWORD` | 是 | 数据库密码 |
| `DB_NAME` | 是 | 数据库名 |
| `JWT_SECRET_KEY` | 是 | 签名密钥，**>= 32 字符**；可用 `python -c "import secrets; print(secrets.token_urlsafe(48))"` 生成 |
| `SMTP_PASSWORD` | 否* | QQ 邮箱 SMTP 授权码（*需要发邮件时填） |
| `CRON_KEY` | 否* | 定时任务访问密钥（*部署调度端时填） |

> 启动采用 fail-fast：上述 5 个必填项缺失或 `JWT_SECRET_KEY` 过短，程序会拒绝启动并提示缺少哪些字段。

### 方式 B：通过系统环境变量注入（推荐，密码不进磁盘配置文件）

在部署机设置环境变量后，产物目录中的 `.env` 可留空或不放对应字段，程序会优先读取环境变量：

```bat
:: cmd
setx DB_HOST "your-rds-host"
setx DB_PASSWORD "your-db-password"
setx JWT_SECRET_KEY "your-32+-char-secret"
:: ... 其余字段同理
```

```powershell
# PowerShell
$env:DB_HOST   = "your-rds-host"
$env:DB_PASSWORD = "your-db-password"
$env:JWT_SECRET_KEY = "your-32+-char-secret"
```

环境变量优先于 `.env`（pydantic-settings 的默认行为），适合配合密钥管理服务/进程托管注入。

---

## 3. 首次启动前的数据库迁移（AUTO_DDL=false）

生产安全约定：**默认禁止启动时自动建库/改表**（`AUTO_DDL=false`）。
因此拿到新库时，必须**手动**执行迁移 SQL。

后端仓库 `docs/migrations/` 下已提供增量迁移脚本：

```
docs/migrations/
├── 2026-08-11-chunfeng-v1.sql
└── 2026-08-12-chunfeng-indicators-v2.sql
```

迁移步骤：

1. 确认 `.env` 中 `AUTO_DDL=false`（默认，勿在生产开启）。
2. 用 DBA/管理账号连接目标库，按文件时间顺序逐个执行：
   ```bash
   mysql -h <DB_HOST> -u <DB_USER> -p <DB_NAME> < docs/migrations/2026-08-11-chunfeng-v1.sql
   mysql -h <DB_HOST> -u <DB_USER> -p <DB_NAME> < docs/migrations/2026-08-12-chunfeng-indicators-v2.sql
   ```
3. 迁移完成后再启动 `叙阅.exe`。

> 若确实需要程序自动建表（仅限开发/测试库），可临时设 `AUTO_DDL=true`；
> 生产库强烈不建议，DDL 一律走人工审批。

---

## 4. multi_project_settings.json 与 env:VAR 引用

### 单项目（默认）

`dist/叙阅/` 下**不提供**该文件。首次启动时程序依据 `.env`/环境变量自动生成单 profile 配置
（`host/user/password/database` 来自 `DB_*` 字段），文件生成在 exe 同目录，之后可自行编辑。

### 多项目

需要管理多套数据库 profile 时，在 `dist/叙阅/` 下手动创建 `multi_project_settings.json`。
**DB 密码请用 `env:VAR_NAME` 形式引用环境变量，避免明文落盘与随包分发**：

```json
{
  "project_name": "叙阅",
  "active_db_profile_id": "<profile-id>",
  "db_profiles": [
    {
      "id": "<profile-id>",
      "name": "当前环境",
      "host": "<DB_HOST>",
      "port": 3306,
      "user": "<DB_USER>",
      "password": "env:DB_PASSWORD",
      "database": "<DB_NAME>",
      "created_at": "2026-01-01T00:00:00+00:00",
      "updated_at": "2026-01-01T00:00:00+00:00"
    }
  ],
  "updated_at": "2026-01-01T00:00:00+00:00"
}
```

- `password` 为 `env:VAR_NAME` 时，程序启动会从同名环境变量读取真实密码；`VAR_NAME` 未配置会报错提示。
- 字段留空（`""`）表示待填；`active_db_profile_id` 需与某个 profile 的 `id` 一致，否则使用默认配置。
- 该文件同样被 `.gitignore` 忽略，**不得提交到版本库**。

---

## 5. 安全约定（务必遵守）

- `.env`、`multi_project_settings.json`、`.env.production` 均被 `.gitignore` 忽略，**绝不提交**。
- 环境分离：本地开发用 `.env`（DB_* 留空即 fail-closed，宁可起不来也不连生产库）；生产凭据放 `.env.production`（仅部署流程使用），生产环境经环境变量/密钥管理注入。
- 仓库根目录的 `.env.example` 只作字段清单，提交到 git 是安全的；打包脚本会用它生成产物的占位 `.env`。
- 打包脚本 `scripts/build_exe.sh` 会在打包后强制把产物 `.env` 替换为占位版、删除产物中真实的 `multi_project_settings.json`，并断言敏感字段为空——请勿在打包机上放置会被带入产物的真实凭据文件。

---

## 6. 重新打包（开发者）

前置：前端已构建（`grade-buddy-scan-main/dist` 非空）、`/e/anaconda` 环境可用。

```bash
cd 叙阅后端仓库根目录
bash scripts/build_exe.sh
```

脚本会：

1. 校验前端 `dist` 存在且非空；
2. 把 `/e/anaconda/Library/bin` 前置到 PATH（规避 libssl 冲突）；
3. 清理旧 `build/`、`dist/叙阅/`（幂等）；
4. `python -m PyInstaller --noconfirm --clean 叙阅.spec`；
5. 用 `.env.example` 覆盖产物 `.env`、删除产物 `multi_project_settings.json`；
6. 断言产物 `.env` 敏感字段为空后输出交付目录与部署提醒。
