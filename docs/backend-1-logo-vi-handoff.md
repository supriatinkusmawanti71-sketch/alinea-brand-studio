# 后端 1 接线交接：Logo 选择 → VI 决策点

更新时间：2026-07-04

后端 2 已确认 Agent 层具备完整能力：

```text
checkpoint 停在 logo_decision
→ Command(resume=Logo 选择)
→ 校验选中的 Logo
→ Fake/真实文本 Provider 生成 VIOutput
→ checkpoint 停在 vi_decision
```

本文件只定义后端 1 需要接入的业务字段和验收条件，不要求后端 2 修改 Router、业务表或迁移。

## 1. 建议业务 API

```http
POST /api/v1/stage-runs/{logo_run_id}/logo-selection
Content-Type: application/json
```

公开请求：

```json
{
  "version_id": "logo-stage-version-uuid",
  "logo_id": "logo-wordmark"
}
```

前端提交 `logo_id`；应用层转换为 Agent 恢复载荷：

```json
{
  "version_id": "logo-stage-version-uuid",
  "selected_item_id": "logo-wordmark"
}
```

Agent 的正式恢复 Schema 为 `SelectItemDecision`：

```text
version_id: UUID
selected_item_id: string，1–120 字符
```

## 2. 提交前校验

后端 1 必须在 PostgreSQL 事务中校验：

1. 来源 Stage Run 存在、属于当前 workspace。
2. 来源 Run 的 `stage == LOGO` 且 `status == SUCCEEDED`。
3. `version_id == source_run.result_version_id`。
4. Stage Version 属于相同 project、stage 和 source run。
5. `logo_id` 存在于该 Version 的 `output_json.concepts[*].id`。
6. 同一 `source_version_id + action` 尚未存在不同选择。

不能只验证 Logo ID 字符串；必须同时验证 Version ID。

## 3. Decision 记录

复用现有 `decisions` 表，不新增同义表：

```text
stage: LOGO
action: SELECT_VERSION
source_version_id: 请求中的 version_id
selected_item_id: 请求中的 logo_id
resulting_stage_run_id: 新 VI Run ID
created_by: 当前操作者
payload_json:
  version_id
  selected_item_id
```

幂等规则：

- 同一 Logo Version 重复提交相同 Logo：返回原 VI Run。
- 同一 Logo Version 已选择其他 Logo：返回 HTTP 409。
- 不允许再次恢复同一个 `logo_decision` checkpoint。

## 4. 新 VI Stage Run

```text
stage: VI
status: QUEUED
workflow_thread_id: 继承 Logo Run
parent_stage_run_id: Logo Run ID
idempotency_key: select-logo:{logo_version_id}
```

内部 `input_json`：

```json
{
  "resume": {
    "version_id": "logo-stage-version-uuid",
    "selected_item_id": "logo-wordmark"
  },
  "decision_id": "decision-uuid",
  "logo_version_id": "logo-stage-version-uuid"
}
```

网页不得自行拼装或读取 `input_json`。

## 5. Worker 接线

Worker 调用：

```python
Command(resume=stage_run.input_json["resume"])
```

并继续使用：

```python
config={"configurable": {"thread_id": stage_run.workflow_thread_id}}
```

VI Run 成功后：

- 使用 `VIOutput` 校验 `result["vi_output"]`。
- 创建不可变 VI Stage Version。
- `input_refs_json` 至少记录 `brand_spec_version`、`logo_version_id`、`decision_id`。
- VI Run 更新为 `SUCCEEDED` 并写入 `result_version_id`。
- Project `current_stage` 更新为 `VI`。
- checkpoint 的业务状态为 `WAITING_USER`，中断类型为 `vi_decision`。

## 6. VIOutput 字段

```text
schema_version
palette[3..6]
  name
  hex
  usage
typography
  heading_style
  body_style
  fallbacks[1..8]
  usage_rules[1..12]
logo_rules
  clear_space
  minimum_size
  background_rules[1..12]
  prohibited_uses[1..20]
layouts[1..4]
  name
  grid
  spacing
  example_usage
source_logo_asset_id
```

`source_logo_asset_id` 必须等于用户选中的 Logo concept 的 `preview_asset_id`。

## 7. 后端 1 验收

```text
1 条 Logo Decision
1 个 VI Stage Run
1 个 VI Stage Version
1 次 VI 模型调用
0 个新增图片资产
checkpoint = WAITING_USER / vi_decision
```

必须覆盖：正确选择、Version 不匹配、Logo ID 不存在、相同选择重提、不同选择冲突，以及 Worker 重建后恢复。
