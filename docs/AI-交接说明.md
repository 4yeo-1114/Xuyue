# AI 开发交接说明

> 用途：换机器 / 换 agent 后快速接手。读完这份就能继续开发。
> 最后更新：2026-11-18

---

## 一、这是个什么项目

**叙阅（GradeBuddy）** —— 一套 AI 作业/试卷批改系统，卖给学生和学校老师。

| 部分 | 目录 | 说明 |
|---|---|---|
| 后端 | `backend/` | Python 3.11+ / FastAPI，端口 **6888** |
| 前端 | `frontend/` | React + Vite + TypeScript，端口 6889（开发）/ 打包后由后端托管 |
| 小程序 | `miniprogram/` | 微信小程序（家长端），本次开发不涉及 |

**部署形态**：打包成 Windows 本地安装包（自带便携 MySQL + PyInstaller 打包的 `叙阅.exe`），客户双击 `.bat` 安装运行。安装包构建在本文档第六章。

---

## 二、批改链路（最重要，先看这里）

系统有**三条判分链**，客户实际用的是第 1 条。

### 链路 1：智能模型批改（ref_cls）—— **主力，客户在用**

```
标准答案卷 + 学生卷
  → 百度 paper_cut_edu_vlm 切题（拿题目框 + 作答框）
  → 千问 VL 两图对照判分（标准答案图 + 学生作答图）
  → 生成留痕图
```

| 环节 | 函数 | 文件:行 |
|---|---|---|
| 入口 | `grade_reference_vlm_paper` | `reference_vlm_grading.py:8230` |
| 切题 | `submit_paper_cut_vlm` / `extract_vlm_questions` | 同文件 |
| 建判分任务 | `_build_grading_tasks` / `_build_template_grading_tasks` | 同文件 |
| 调千问 | `_call_qwen_for_question_batch` | 同文件 |
| 判定归一化 | `_normalize_decision` | 同文件 |
| 覆盖率哨兵 | `coverage_report` / `ensure_atomicity` | `grading_coverage.py` |

### 链路 2：按标准答案比对（answer_key）—— 答题卡场景

```
答题卡切题 → 逐作答区读学生答案（OMR 墨迹 → 百度 OCR → 千问 VL）
  → 与老师录入的标准答案比对
```

| 环节 | 函数 | 文件:行 |
|---|---|---|
| 任务入口 | `_run_answer_key_grade_impl` | `router.py:12840` |
| 核心判分 | `grade_paper_by_answer_key` | `answer_key_grading.py:1383` |
| 答案解析 | `parse_answer_key_text` | 同文件 |
| 选择题识读 | `_omr_choice_answer` / `_ocr_choice_answers` / `_vl_read_choice_answer_detailed` | 同文件 |

### 链路 3：作文批改

`essay_grading.py:516` `grade_essay_with_qwen`。

### 留痕图（两条链共用）

| 函数 | 文件:行 | 说明 |
|---|---|---|
| `draw_real_marks_and_save` | `pipeline.py:986` | 原卷 + 红笔批注 |
| `draw_marks_only_and_save` | `pipeline.py:1053` | **纯留痕白底图**（打印/PDF 用，客户确认这是预期） |
| `_draw_result_mark` / `_draw_manual_result_mark` | `pipeline.py` | √ / × / ○(未作答) / **(待确认)** |

---

## 三、已经修好的缺陷（别重复踩）

每个都写了「现象 → 根因 → 修复位置」。**改之前先确认这些修复还在（`git log` 看提交）。**

### P0-1 百度 VLM 作答框字段读错 → 全卷 0 个作答槽

- **现象**：✓/× 落在题干行尾，填空题完全没批改痕迹
- **根因**：官方返回是 `location.ans[i].ans_location`，代码读的是 `location.ans_location`（不存在）
- **修复**：`_answer_locations_from_raw()` 兼容三种形态
- **验证**：真卷实测作答框 0 → 40

### P0-2 题号口径错位 → 整体错一格

- **现象**：修好 P0-1 后准确率反而降到 37.9%，学生答案对到了别的题
- **根因**：`only_split=true` 不返回题干文字，`display_index` 只是返回顺序；卷首「1–15 答题表格」被当成第 1 题
- **修复**：`_printed_number_candidates()` + `_anchor_printed_numbers()`，按卷面印刷题号锚定
- **约束**：**不设任何固定题号区间**

### P0-3 答案表与题号整体错行 → 判错成对

- **现象**：第 16–25 题整体错开一行，学生写 be/have/2s 也打 ✓
- **根因**：答案表条目 `printed_no` 与答案文本内嵌题号不一致
- **修复**：
  - `_answer_entry_number_offset()` 检测整体偏移
  - `_align_answer_entry_numbers()` 按内联题号重编号（`_ANSWER_TABLE_EXTRACT_VERSION` 已升到 6，旧缓存自动重建）
  - `_verify_answer_against_standard()` 判对前确定性校验

### P0-4 判对无校验

- **修复**：`_verify_answer_against_standard()` —— 学生作答与标准答案既非精确匹配、也不在编辑距离内 → 驳回为待确认
- **边界**：`不做功` vs `做功` 必须拦截；简答（中文≥10字/英文≥25字符）不做逐字校验；`A|B` 多解任一命中即放行

### P1-1 填空答案解析截断

- **现象**：`1. 0.5` 解析成 `0`，造出幽灵题号
- **修复**：重写为「按题号起点切段 + 题号递增」，答案体不按字符集截断

### P1-2 多空题只消费第一空

- **修复**：`_expected_blanks_for_block()` 收集 `N_1..N_k`；块自带独立空号时不合并

### P1-3 第 14 题 100% 漏判

- **根因**：跨页题目被当成孤立的底行跳过，且「未判定」静默消失
- **修复**：`grading_coverage.py` 逐题比对「应有题号 vs 已判定题号」，缺题进结果文本 + 标待确认

### P1-4 手写字母读成印刷选项字母

- **修复**：`_bracket_crop_box()` 只读括号区域；`_vl_read_choice_answer_detailed()` 双读一致才下结论；置信度 <0.6 转人工；连续 ≥3 题判错自动标复核

### P1-5 静默跳过无痕迹

- **修复**：所有失败路径必须 `read_uncertain=True` + `reason` + `result="待确认"` + 打印日志
- 留痕图上**待确认画红色「?」**（以前什么都不画，老师以为漏批）

### P2-1 云端打印 P1/P2 反了

- **现象**：云端打印 P1 出现在第二页
- **根因**：PDF 路径套用了 GDI 直打才需要的「反顺序对调」；PDF 是按页序出纸的
- **修复**：`duplex_submission_paths()` 只排序**不对调**；`_duplex_job_paths()`（GDI 路径）保留块内对调
- **注意**：GDI 路径的对调是打印机驱动依赖，`GRADING_DUPLEX_SWAP_SIDES=0` 可关闭

### P2-2 留痕文件名页码解析失效

- **现象**：每人 P1/P2 相反、打印顺序与页面不一致
- **根因**：文件名结尾是 `_1_wa.jpg`，正则 `_(\d+)$` 匹配不到 → 页码恒为 1、同一学生被拆成两个
- **修复**：`_marks_stem()` 先剥 `_wa`/`_nocomment` 变体后缀

### P2-3 划掉重写导致留痕混乱（? 和 ✓/× 混在一起）

- **需求**：学生划掉旧答案再写新的 → **只批改新的**
- **修复**：
  - 三条链提示词都加了 `STRIKETHROUGH / CORRECTION` 规则
  - 确定性兜底：`_ambiguous_multi_candidate()`（智能链）/ `_looks_like_multiple_candidates()`（答案比对链）—— 短答案里出现多个候选 → 待确认
  - 多空题标准答案本身是多段时不误判

---

## 四、开发硬性规范

1. **不确定宁可不判**：显式 `result="待确认"` + 写明原因，**绝不允许静默跳过**。
2. **禁止纸面专属硬编码**：不要固定题号区间（如 9–14）、固定空数、固定像素阈值。
3. **判对必须有依据**：任何 `correct` 判定都要么模型给出、要么确定性校验通过。
4. **改判分逻辑前后各跑一次测试对比**，不允许让失败数增加。
5. **只改本仓库**。

### 测试基线

```powershell
cd backend
python -m pytest tests/ -q
# 基线：34 failed / 1187 passed / 35 skipped
```

**这 34 个失败是既有问题，不要修**（修了会浪费大量时间且可能引入风险）：
- `test_reference_vlm_grading.py` 4 条：缺 `backend/试卷切题与识别/` 测试样本目录
- `test_public_register.py` 16 条：注册模块既有问题
- `test_redline_*.py` 4 条：`get_qwen_config` 属性缺失
- 其余：`test_ai_chat_history` / `test_essay_rubric_dimensions` / `test_ocr_enhance` 等既有问题

**判断是否引入回归**：只看失败数有没有超过 34。

### 本次新增的测试（全绿，共 160 条）

| 文件 | 覆盖 |
|---|---|
| `test_grading_core_rules.py` | 答案解析 / 归一化 / 字母集合 / 多空拆分 / 待确认留痕 |
| `test_answer_table_alignment.py` | 答案表错行矫正 + 判对确定性校验 |
| `test_choice_letter_reading.py` | 括号定位 / 双读一致 / 置信度 / 连续错判复核 |
| `test_grading_coverage.py` | 覆盖率统计 / 原子性标记 |
| `test_print_marks_order.py` | `_wa` 文件名 / 双面排序 / 留痕可见性 |
| `test_strikethrough_and_cloud_print.py` | 云端打印页序 / 划掉重写多候选 |

---

## 五、诊断脚本（只读，可以删）

在 `backend/` 下，用于跑真实试卷复现问题：

| 脚本 | 用途 |
|---|---|
| `_all_subjects.py` | 7 个科目各取一份真卷跑完整链路，统计漏批/待确认 |
| `_choice_ab.py` | 选择题前后对比（含人工核对基准答案） |
| `_fillin_ab.py` | 填空题前后对比（自动用 git HEAD 旧版作对照） |
| `_probe_chain.py` / `_dump_manual.py` | 单步调试：切题 / OCR / OMR 中间结果 |

**密钥来源**：这些脚本从 `D:\叙阅本地化安装包_20261116\app\.env` 读百度/千问密钥。换机器后需要改路径，或直接设环境变量 `BAIDU_API_KEY` / `BAIDU_SECRET_KEY` / `DASHSCOPE_API_KEY`。

**测试素材**：仓库根目录 `手写试卷/`（7 个班级的真实扫描卷）、`11.17英语AI批改结果/`、`出现的问题/`（客户反馈截图）。

---

## 六、打包安装包

客户用的是「本地化安装包」形态：便携 MySQL + PyInstaller 打包的 exe + 一键脚本。

### 构建步骤

```powershell
# 1. 准备 Python 3.12 构建环境（旧包 _internal 是 cp312，版本必须一致）
cd D:\xuyue\_build_tmp
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r ..\xuyue\backend\requirements.txt
uv pip install --python .venv/Scripts/python.exe pyinstaller pywin32

# 2. 前端（有改动才需要）
cd D:\xuyue\xuyue\frontend
npm install && npm run build

# 3. 后端 exe
cd D:\xuyue\xuyue\backend
$env:FRONTEND_DIST = "D:\xuyue\xuyue\frontend\dist"
$env:PATH = "D:\xuyue\_build_tmp\.venv\Scripts;$env:PATH"
python -m PyInstaller --noconfirm --clean 叙阅.spec

# 4. 换进包骨架 app\ 目录，压缩（中文文件名必须按 GBK 写，见 make_zip.py）
```

### 已修复的打包问题（都是真实踩过的坑）

1. **`requirements.txt` 缺 matplotlib** —— `app/utils/figure_render.py` 模块级 import，缺了就启动崩溃。已补。
2. **端口写死 3306** —— 客户机器上有 MySQL80 时会撞端口，且脚本把别人的库当自己的（报 1045）。已改为 `gen_db_port.ps1` 自动找空端口（3306→3325），写入 `db_port.txt` / `my.ini` / `app\.env`。
3. **`taskkill /f /im mysqld.exe`** —— 会杀掉客户自己的 MySQL80。已改为 `mysqladmin shutdown` + 按 PID 兜底。
4. **中文文件名** —— 用 Python `zipfile` 按 GBK 写入、不设 UTF-8 标志位，否则解压乱码。

### 花名册

`setup\seed_roster.sql` 由 `初一花名册.zip` / `初二花名册(1).zip` 生成（64 个班、3184 人）。
- **幂等**：按「年级+班名」判重，重跑不重复
- **整班替换**：先清空该班原学生再灌入（否则演示数据和真实数据混在一起变成 100 人/班）
- `一键启动.bat` 每次启动自动执行

---

## 七、已知风险 / 待办

### 需要客户样本验证

1. **划掉重写的识别效果** —— 提示词改得再明确也依赖模型。需要用客户反馈的那几张卷（有划掉痕迹的）实测。若还有问题，把具体卷子拿来针对性调。
2. **准确率只有一份卷有人工标答**（2105 科学卷 15 题，修复后 100%）。其余科目只验证了「不漏批」，准确率未验证。建议每科抽 2 份让老师标答案后复测。

### 配置层面

3. **QPS 偏离百度官方限制** —— 文档写 create_task QPS=2、get_result QPS=10，代码默认 30。高并发会撞 `error_code=18`。建议 `.env` 设 `BAIDU_CREATE_QPS=2`。
4. **图片未按文档 urlencode** —— 目前靠 JSON body + JPEG 压缩能用，大图有风险。
5. **错误码覆盖不全** —— 216201（图片格式）/216630（识别失败）未单独映射中文提示。

### 其他

6. **GDI 打印 P1/P2** 取决于打印机驱动送纸顺序，代码无法自动判断。默认补偿对调；反向的话设 `GRADING_DUPLEX_SWAP_SIDES=0`。
7. **`gitee` 远程**：迁移后请确认 `git remote -v` 指向新地址。

---

## 八、环境变量速查

| 变量 | 默认 | 说明 |
|---|---|---|
| `VERDICT_CACHE` | `0` | 判分缓存，默认关 |
| `SLOT_ROLE_FILTER` | `1` | 题干假块过滤（只在百度智能批改链生效） |
| `GRADING_DUPLEX_SWAP_SIDES` | `1` | GDI 双面反顺序送打；`0` 关闭 |
| `BAIDU_CREATE_QPS` | `30` | 建议按官方改成 `2` |
| `BAIDU_GET_RESULT_QPS` | `30` | 建议按官方改成 `10` |
| `REFERENCE_VLM_QWEN_WORKERS` | 自适应 6/8 | 千问并发 |
| `MARK_RIGHT_SHIFT_PX` | `28` | 留痕符号右移像素 |

---

## 九、快速上手 checklist

新机器第一步：

```powershell
cd D:\xuyue\xuyue\backend
python -m pytest tests/ -q        # 确认 34 failed / 1187 passed
```

然后：

1. 读本文档第二章（批改链路）和第四章（开发规范）
2. 打开 `grading_coverage.py` 和 `test_strikethrough_and_cloud_print.py`，理解「不留静默漏批」这个贯穿全项目的原则
3. 有客户新反馈时，先到 `出现的问题/` 看截图，再到 `手写试卷/` 找对应真卷复现
4. 改完跑全量测试，失败数不超过 34 才算通过
