# 前端 1 接口交接：项目与 Intake

更新时间：2026-07-04
负责人：后端 2 提供 Agent 结果契约；后端 1 后续维护业务 API/OpenAPI。

## 本轮前端目标

```text
创建项目
→ 轮询 Intake Run
→ 展示 AI 补问
→ 提交答案
→ 获得 Directions Run
→ 继续轮询直到成功
```

统一 API 前缀：`/api/v1`。浏览器优先通过 `http://localhost:8080` 访问；本地直连 API 为 `http://localhost:8000`。

## 1. 创建项目

```http
POST /api/v1/projects
Content-Type: application/json
```

最小请求：

```json
{
  "name": "示例品牌",
  "requirement_text": "希望做一个现代、清爽的茶饮品牌。",
  "structured_fields": {},
  "reference_artifact_ids": []
}
```

`structured_fields` 当前允许：

```text
industry
brand_background
target_audiences
price_positioning
brand_personality
style_keywords
required_elements
prohibited_elements
competitor_notes
slogan
language
```

成功返回 HTTP 201：

```json
{
  "project": {
    "id": "uuid",
    "workspace_id": "local-workspace",
    "name": "示例品牌",
    "current_stage": "INTAKE",
    "status": "ACTIVE",
    "version": 1,
    "created_at": "UTC ISO 8601",
    "updated_at": "UTC ISO 8601"
  },
  "stage_run": {
    "id": "uuid",
    "project_id": "uuid",
    "stage": "INTAKE",
    "status": "QUEUED",
    "attempt": 0,
    "error_code": null,
    "result_version_id": null
  }
}
```

前端保存 `project.id` 和 `stage_run.id`，立即进入任务轮询。

## 2. 轮询 Stage Run

```http
GET /api/v1/stage-runs/{stage_run_id}
```

运行状态只有：

```text
QUEUED
RUNNING
SUCCEEDED
FAILED
```

建议每 1–2 秒轮询一次；进入 `SUCCEEDED` 或 `FAILED` 后停止。

Intake 成功但资料不足时，`result` 示例：

```json
{
  "schema_version": 1,
  "ready": false,
  "questions": [
    {
      "id": "missing-industry",
      "field_path": "industry",
      "prompt": "品牌所在的行业或品类是什么？",
      "reason": "行业会影响视觉语境和竞品区分。",
      "required": true,
      "answer_type": "TEXT",
      "options": []
    }
  ],
  "brand_spec_patch": {},
  "suggestions": [],
  "conflicts": []
}
```

表单组件根据 `answer_type` 渲染：

```text
TEXT          单行或多行文本
TEXT_LIST     字符串列表
SINGLE_CHOICE 单选，使用 options
MULTI_CHOICE  多选，使用 options
```

不要根据问题标题猜字段；提交时原样使用 `field_path`。

## 3. 提交 Intake 答案

```http
POST /api/v1/stage-runs/{intake_run_id}/intake-answers
Content-Type: application/json
```

请求：

```json
{
  "answers": [
    {"field_path": "industry", "value": "精品茶饮"},
    {"field_path": "brand_background", "value": "城市东方茶饮品牌"},
    {"field_path": "target_audiences", "value": ["年轻城市消费者"]},
    {"field_path": "style_keywords", "value": ["当代", "东方", "清爽"]}
  ]
}
```

成功返回 HTTP 202，得到新的 Directions Run：

```json
{
  "id": "directions-run-uuid",
  "parent_stage_run_id": "intake-run-uuid",
  "workflow_thread_id": "workflow-thread-uuid",
  "project_id": "project-uuid",
  "stage": "DIRECTIONS",
  "status": "QUEUED"
}
```

前端改为轮询新返回的 `id`，不能继续轮询旧 Intake Run 等待 Directions。

相同答案重复提交会返回原 Directions Run，不会重复生成。

## 4. 项目列表与刷新恢复

```http
GET /api/v1/projects
GET /api/v1/projects/{project_id}
```

项目详情包含：

```text
project 基础字段
brand_spec
stage_runs
```

页面刷新后：

1. 读取项目详情。
2. 从 `stage_runs` 找最新任务。
3. `QUEUED/RUNNING` 继续轮询。
4. `SUCCEEDED` 根据 `stage` 和 `result_version_id` 展示对应阶段。
5. `FAILED` 展示 `error_code/error_message`，不要读取 Celery 或 checkpoint。

## 5. 错误处理

```text
POST /projects 422：表单或 BrandSpec 字段错误
POST /intake-answers 409：Run 状态、归属或恢复条件冲突
GET 404：项目或任务不存在
Stage Run FAILED：读取 error_code 和 error_message
```

## 6. 本轮禁止事项

- 不直接读取 PostgreSQL、Redis、Celery 或 checkpoint。
- 不在前端拼装 `workflow_thread_id` 或内部 `input_json`。
- 不手写第二套 DTO；以 `/api/openapi.json` 为准。
- 不把 `title/summary` 假方向字段当成正式 Directions 契约。
- 不在本轮实现 Direction 选择页面；该部分属于前端 2。
