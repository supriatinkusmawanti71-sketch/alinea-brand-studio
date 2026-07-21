# 后端 1 接线交接：Materials 确认 → Review 决策点

更新时间：2026-07-04

## 1. Agent 流程

```text
checkpoint = material_decision
→ ConfirmStageDecision
→ generate_review
→ ReviewOutput
→ checkpoint = review_decision
```

恢复载荷：

```json
{
  "version_id": "materials-version-uuid",
  "confirmed": true
}
```

正式 Schema：

```text
ConfirmStageDecision
  version_id: UUID
  confirmed: 只能为 true
```

## 2. 建议业务 API

```http
POST /api/v1/stage-runs/{materials_run_id}/materials-confirmation
Content-Type: application/json
```

```json
{
  "version_id": "materials-version-uuid",
  "confirmed": true
}
```

成功后返回新的 Review Run，网页继续轮询 Review Run ID。

## 3. 提交前校验

1. Materials Run 存在且属于当前 workspace/project。
2. `stage == MATERIALS` 且 `status == SUCCEEDED`。
3. `version_id == materials_run.result_version_id`。
4. Materials Version 属于相同 project、stage 和 source run。
5. `MaterialOutput` 包含恰好 2 个 Scene 和 2 个唯一资产。
6. `confirmed` 只能为 `true`。

## 4. Decision

复用现有 `decisions` 表：

```text
stage: MATERIALS
action: CONFIRM_VERSION
source_version_id: Materials Version ID
selected_item_id: null
resulting_stage_run_id: Review Run ID
created_by: 当前操作者
payload_json: {version_id, confirmed}
```

同一 Materials Version 重复确认返回原 Review Run，不得重复调用审稿模型。

## 5. Review Stage Run

```text
stage: REVIEW
status: QUEUED
workflow_thread_id: 继承 Materials Run
parent_stage_run_id: Materials Run ID
idempotency_key: confirm-materials:{materials_version_id}
```

内部 `input_json`：

```json
{
  "resume": {
    "version_id": "materials-version-uuid",
    "confirmed": true
  },
  "decision_id": "materials-confirm-decision-uuid",
  "materials_version_id": "materials-version-uuid"
}
```

网页不得读取或拼装 `input_json`。

## 6. Review 模型输入

Agent 会读取已确认链路中的：

```text
brand_spec
direction_output
logo_output
vi_output
ip_output（跳过 IP 时为 null）
material_output
material_asset_ids（2 个 Material preview_asset_id）
```

Review 不生成图片或新资产，只调用 1 次文本模型。

## 7. ReviewOutput 正式 JSON

```text
schema_version
pass
summary
issues[]
  id
  severity: BLOCKER | WARNING | INFO
  category
  evidence
  suggestion
  target_stage
  target_asset_ids[]
```

重要：Pydantic 内部属性名是 `passed`，但正式 JSON 键固定为：

```json
{"pass": true}
```

API、OpenAPI、前端类型和共享 fixture 都必须使用 `pass`，不要发布 `passed`。

Review Category：

```text
BRAND_CONSISTENCY
LOGO_USAGE
COLOR
TYPOGRAPHY
IP_CONSISTENCY
MATERIAL_CONTENT
TEXT_ERROR
MISSING_ASSET
CORRUPTED_FILE
SECURITY
PERMISSION
```

## 8. Worker 成功写入

Review Run 成功后：

- 使用 `ReviewOutput` 校验 `result["review_output"]`。
- 按 alias 输出 JSON，必须保存 `pass`。
- 创建不可变 Review Stage Version。
- `input_refs_json` 至少记录 `materials_version_id` 和 `decision_id`。
- 写入 1 条 Review 文本模型调用记录。
- 不创建 Artifact。
- Stage Run 更新为 `SUCCEEDED`。
- Project `current_stage = REVIEW`。
- checkpoint 为 `WAITING_USER / review_decision`。

## 9. 下一次恢复载荷

Review 页面提交：

```json
{
  "version_id": "review-version-uuid",
  "proceed": true,
  "accepted_issue_ids": []
}
```

对应 Agent Schema 为 `ReviewDecision`。

普通品牌一致性 Warning 可以由用户接受风险；以下问题不能绕过：

```text
SECURITY
PERMISSION
MISSING_ASSET
CORRUPTED_FILE
```

该强制规则由后端 1 在业务 API 层校验，不能只相信前端按钮状态。

## 10. 后端 1 验收

```text
Materials Confirm Decision：1
Review Run：SUCCEEDED
Review Stage Version：1
Review 模型调用：1 条文本
新增 Artifact：0
正式结果字段：pass，不是 passed
checkpoint：WAITING_USER / review_decision
```

必须覆盖：Version 不匹配、Material 资产缺失、重复确认幂等、模型输出非法修复，以及 Worker 重建后恢复。
