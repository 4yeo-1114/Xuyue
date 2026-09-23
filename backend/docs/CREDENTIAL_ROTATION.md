# 生产凭据轮换清单

**生成日期**：2026-08-20

**背景**：2026-08-13 发现 PyInstaller 打包产物 `dist/叙阅/` 曾把真实生产凭据随包带出。泄露源是打包产物内的 `.env` + `multi_project_settings.json`。轮换完成前，这些凭据不能假设未外泄。

**本文件只列字段、存放位置、步骤，不含任何明文值。**

## 一、泄露凭据与轮换优先级

| 凭据                         | 存放位置                                                                                                                           | 影响                                  | 优先级                             |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------- | ---------------------------------- |
| 阿里云 RDS MySQL 密码        | `.env.production` → `DB_PASSWORD`；`multi_project_settings.json` → 3 个 db_profile 的 `password`（**grade/ky/hn 同 host 同密码**） | 3 个生产库全部暴露                    | **P0**                             |
| QQ 邮箱 SMTP 账号 + 授权码   | `.env.production` → `SMTP_USERNAME` / `SMTP_PASSWORD`                                                                              | 可冒名发信（泄露授权码 = 任意发邮件） | **P0**                             |
| JWT_SECRET_KEY（64 位）      | `.env.production` → `JWT_SECRET_KEY`                                                                                               | 可伪造任意用户 token                  | **P1**（全量用户掉线重登，需低峰） |
| CRON_KEY（定时任务访问密钥） | `.env.production` → `CRON_KEY`                                                                                                     | 可伪造调度请求                        | P1                                 |
| 多项目 DB 密码               | 即 RDS 密码（同一值），已并入第一行                                                                                                | —                                     | 已并入                             |

**注意**：`multi_project_settings.json` 的 3 个 db_profile（叙阅 grade / ky / 河南客户 hn）指向同一个 RDS 实例、**共用同一密码**。轮换 RDS 密码必须同步 `.env.production` + 该文件 3 处 profile，共 4 个位置。

## 二、轮换步骤

### 1. RDS MySQL 密码（P0）

1. 登录阿里云控制台 → RDS 实例 → 账号管理 → `grade` 账号 → 重置密码
2. 生成新强密码（≥20 位混合，避免与旧密码相似）
3. 同步两处：
   - `.env.production` 的 `DB_PASSWORD`
   - `multi_project_settings.json` 的 3 个 db_profile `password`（同一新值）
4. 验证：用新密码分别连 grade / ky / hn 三个库
5. 风险：改密码后所有旧连接立即失效。改前确认没有测试/预发环境还在用旧密码；建议低峰操作

### 2. QQ 邮箱 SMTP 授权码（P0）

1. QQ 邮箱 → 设置 → 账户 → 安全 → 重新生成授权码
2. 同步 `.env.production` 的 `SMTP_PASSWORD`（若换邮箱，`SMTP_USERNAME`/`SMTP_FROM` 一并改）
3. 验证：发一封测试邮件走通 STARTTLS
4. 风险：旧授权码立即失效；生产服务需用新值重启

### 3. JWT_SECRET_KEY（P1）

1. 生成新密钥：`python -c "import secrets; print(secrets.token_hex(32))"`（64 位 hex）
2. 同步 `.env.production` 的 `JWT_SECRET_KEY`
3. 验证：重启服务后新 token 签发与校验正常
4. 风险：**所有已登录用户会掉线重新登录**，必须在低峰操作

### 4. CRON_KEY（P1）

1. 生成新随机值（≥32 位）
2. 同步 `.env.production` 的 `CRON_KEY`，并同步调度端配置（如有外部 cron 调用方）
3. 验证：调度端用新密钥调用一次定时任务接口

## 三、改后必做

- 上述凭据全部轮换后，确认 `.env.production` / `multi_project_settings.json` 已用新值 → 重跑 `scripts/build_exe.sh` 重打包（产物已内置占位 `.env` 替换 + 敏感字段非空断言，不会再带出真实凭据）
- 本地开发**不受影响**：本地 `.env` 指向本地容器 `grade-buddy-mysql`（127.0.0.1:13307），与生产凭据无关
- 建议轮换后 1~2 周观察：登录、邮件发送、定时任务是否正常

## 四、未确认泄露（可选审查）

- **百度 BAIDU / DashScope key**：存于 `system_settings` 数据库表（应用界面配置），不在打包产物 `.env` 内，未确认泄露。若曾把完整数据库导出分发过，建议一并重置
- 若后续发现其他 `.env` 键（如 SMTP_USERNAME 变更）也随包带出，按同类流程处理
