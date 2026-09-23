# 叙阅 · 作业打印小程序

老师在小程序里布置作业 → 生成 A4 作业纸 → 办公室电脑上的打印代理自动取件打印。

**本期范围**：只做「布置 + 打印」，不含批改、不存留任何作业记录（打印队列在内存里，后端一重启就清空）。

---

## 一、三个部分

| 部分 | 位置 | 作用 |
|------|------|------|
| 小程序 | 本目录 | 老师操作界面 |
| 后端打印队列 | `grade-buddy-scan-back_end/app/routers/print_jobs.py` | 生成作业纸 PDF、排队 |
| 打印代理 | `D:\job2\print_agent.py` | 在连着打印机的电脑上跑，取任务→打印 |

## 二、先跑通本机（推荐按这个顺序）

### 1. 启动后端

```bash
cd D:\job2\批改君\grade-buddy-scan-back_end
D:\anconda\python.exe run.py
```

确认能访问 <http://127.0.0.1:6888/api/v1/auth/me>（返回 401 就是正常的）。

### 2. 启动打印代理

```bash
# 看本机有哪些打印机
D:\anconda\python.exe D:\job2\print_agent.py --list-printers

# 启动（会每 3 秒向云端要一次任务）
D:\anconda\python.exe D:\job2\print_agent.py
```

配置文件在 `D:\job2\print_agent.ini`，两个地方要确认：

- `[server] url` —— 本地联调改成 `http://127.0.0.1:6888`
- `[server] token` —— 必须和后端 `.env` 里的 `PRINT_AGENT_TOKEN` 一模一样
- `[printer] name` —— 打印机名字（留空 = 用系统默认打印机）
- `[printer] method` —— `raw`（推荐）/ `printto` / `shell`

### 3. 打开小程序

1. 用微信开发者工具「导入项目」，目录选本目录
2. AppID 可以先选「测试号」
3. **详情 → 本地设置 → 勾选「不校验合法域名」**（否则连不上后端）
4. 编译运行，用与网页版相同的账号登录

想连本地后端，把 `utils/config.js` 里的 `apiBase` 改成 `http://127.0.0.1:6888/api/v1`。

## 三、部署到线上

小程序最终要连线上后端，所以后端那三个文件得同步到服务器：

- `app/routers/print_jobs.py`（新增）
- `app/utils/worksheet_pdf.py`（新增）
- `app/config.py`（新增了 `PRINT_AGENT_TOKEN` 字段）
- `app/main.py`（注册路由）

服务器 `.env` 里加一行：

```
PRINT_AGENT_TOKEN=<和 print_agent.ini 里填的一样>
```

然后重启后端：`systemctl restart gradebuddy`

> ⚠️ `config.py` 的 `Settings` 是严格模式（pydantic-settings 默认 `extra="forbid"`），
> `.env` 里多一个它不认识的变量后端就会起不来。所以「加 .env 变量」和「加 config.py 字段」
> 必须同时做。

## 四、打印方式怎么选

| 方式 | 说明 | 适用 |
|------|------|------|
| `raw` | 把 PDF 原样直传给打印机 | 理光 / 柯尼卡等复合机，最快、无弹窗。**默认** |
| `printto` | 调 Adobe Reader 的「打印到」动作 | 装了 Adobe Reader 的机器 |
| `shell` | 交给系统默认 PDF 程序 | 最通用，但可能弹窗 |

`raw` 打不出来（打印机不支持 PDF 直接打印）时，改成 `printto` 或 `shell` 再试。

## 五、常见问题

| 现象 | 处理 |
|------|------|
| 小程序里点打印一直「排队中」 | 打印代理没启动，或代理连的不是同一个后端地址 |
| 代理报「令牌无效」 | `print_agent.ini` 的 token 和服务器 `.env` 的 `PRINT_AGENT_TOKEN` 不一致 |
| 代理报「连不上云端」 | 这台电脑上不了网，或 `[server] url` 写错了 |
| 打印机不出纸 | 看打印机面板是否有报错；换个 `method` 再试 |
| 小程序请求失败 | 没勾「不校验合法域名」，或 `apiBase` 写错了 |

## 六、目录说明

```
grade-buddy-miniprogram/
├── app.js / app.json / app.wxss     小程序入口与全局样式
├── project.config.json
├── utils/
│   ├── config.js                    后端地址、学科年级选项（部署时改这里）
│   └── api.js                       接口封装
└── pages/
    ├── login/                       登录
    ├── index/                       布置作业（主页面）
    ├── result/                      打印状态 + 预览 + 再打一份
    └── history/                     打印记录
```
