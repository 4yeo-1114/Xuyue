# API 接口规范文档

> 供 Python/FastAPI 工程师参考实现

## 基本信息

- **旧 Base URL**: `{VITE_API_BASE_URL}/api/v1`（班级/学生等元数据）
- **批改服务 Base URL**: `{VITE_GRADING_API_BASE_URL}`（默认 `http://localhost:8001`）
- **认证方式**: 旧接口使用 Supabase JWT Token；批改服务当前无鉴权
- **响应格式**: 批改服务统一 `{ ok: true/false, ... }`

---

## 一、批改服务接口（FastAPI · 端口 8001）

### 1.1 单张批改（不参照标准答案）

```
POST /api/grade
Content-Type: multipart/form-data
```

| 字段 | 类型 | 说明 |
|------|------|------|
| file | File | 图片（jpg/jpeg/png/webp） |

**成功 200：**

```json
{
  "ok": true,
  "result": "总评与逐题讲解的文本",
  "image_original": "/modify/original_xxx.jpg",
  "image_annotated": "/modify/annotated_xxx.jpg",
  "image_marks_only": "/modify/marks_only_xxx.jpg"
}
```

---

### 1.2 批量批改（不参照标准答案）

```
POST /api/grade-batch
Content-Type: multipart/form-data
```

| 字段 | 类型 | 说明 |
|------|------|------|
| files | File[] | 多张图片（同名 key） |

**成功 200：**

```json
{ "ok": true, "batch_id": "uuid", "total": 3 }
```

**轮询进度：**

```
GET /api/grade-batch/{batch_id}
```

```json
{
  "ok": true,
  "total": 3,
  "completed": [
    {
      "index": 0,
      "name": "原始文件名.jpg",
      "image_original": "/modify/original_xxx.jpg",
      "image_annotated": "/modify/annotated_xxx.jpg",
      "image_marks_only": "/modify/marks_only_xxx.jpg",
      "result": "总评与逐题讲解文本",
      "marks_only_filename": "marks_only_xxx.jpg"
    }
  ],
  "failed": [
    { "index": 1, "name": "某文件.jpg", "msg": "批改失败原因" }
  ]
}
```

完成条件：`completed.length + failed.length >= total`

---

### 1.3 文件管理（文件夹 + 标准答案）

> 路径中 `{folder_name}` 需 URL 编码

#### 列出所有文件夹

```
GET /api/file-manage/folders
```

#### 新建文件夹

```
POST /api/file-manage/folders
Body: { "name": "语文期末" }
```

#### 列出文件夹内图片

```
GET /api/file-manage/folders/{folder_name}/files
```

```json
{
  "ok": true,
  "files": [
    { "name": "学生1.jpg", "url": "/api/file-manage/folders/xxx/file/学生1.jpg" }
  ],
  "standard_answer": {
    "name": "标准答案",
    "filename": "标准答案.jpg",
    "url": "/api/file-manage/folders/xxx/file/标准答案.jpg"
  }
}
```

#### 上传图片到文件夹

```
POST /api/file-manage/folders/{folder_name}/upload
Content-Type: multipart/form-data
```

| 字段 | 类型 | 说明 |
|------|------|------|
| file | File | 图片文件 |
| is_standard_answer | string | 可选，`true`/`1`/`yes` 标记为标准答案 |

#### 删除文件夹内图片

```
POST /api/file-manage/folders/{folder_name}/delete
Body: { "filenames": ["a.png", "b.jpg"] }
```

#### 获取文件（二进制流）

```
GET /api/file-manage/folders/{folder_name}/file/{filename}
```

---

### 1.4 参照标准答案批改

#### 发起批改

```
POST /api/file-manage/folders/{folder_name}/grade-by-reference
```

```json
{ "ok": true, "job_id": "uuid", "total": 5 }
```

#### 轮询进度

```
GET /api/file-manage/folders/{folder_name}/grade-by-reference/status/{job_id}
```

完成条件：`completed.length + failed.length >= total`

---

### 1.5 打印（仅本地部署可用）

#### 单张打印

```
POST /api/print-marks
Body: { "filename": "marks_only_xxx.jpg" }
```

#### 批量打印

```
POST /api/print-marks-batch
Body: { "filenames": ["marks_only_xxx.jpg", "marks_only_yyy.jpg"] }
```

```json
{ "ok": true, "printed": 2, "errors": [] }
```

---

## 二、旧接口（元数据 · 端口 8081）

### 统一响应格式

```json
{ "code": 200, "message": "success", "data": { ... } }
```

### 2.1 获取班级列表

```
GET /api/v1/classes?grade_id={grade_id}
Authorization: Bearer {supabase_jwt}
```

### 2.2 获取学生列表

```
GET /api/v1/students?class_id={class_id}
Authorization: Bearer {supabase_jwt}
```

---

## 三、架构分工

| 功能 | 负责方 |
|------|--------|
| 用户认证、班级/学生/成绩/题库/资源 | Lovable Cloud（数据库 + Storage） |
| AI 批改、OCR、文件夹管理 | FastAPI 批改服务（端口 8001） |
| 打印控制 | FastAPI 批改服务（仅本地部署） |

## 四、图片路径说明

接口返回的 `image_original`、`image_annotated`、`image_marks_only`、`url` 均为相对路径，前端需拼接：

```
完整 URL = VITE_GRADING_API_BASE_URL + 相对路径
```

## 五、环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `VITE_API_BASE_URL` | 旧 FastAPI 地址 | `http://localhost:8081` |
| `VITE_GRADING_API_BASE_URL` | 批改服务地址 | `http://localhost:8001` |
