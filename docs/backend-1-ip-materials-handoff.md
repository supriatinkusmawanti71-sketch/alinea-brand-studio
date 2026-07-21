# 后端 1 接线交接：IP 确认/跳过 → Materials 决策点

更新时间：2026-07-04

## 1. 两条 Agent 路径

### 已生成 IP

```text
checkpoint = ip_decision
→ ConfirmStageDecision
→ generate_materials
→ 2 个 Material scenes
→ checkpoint = material_decision
```

恢复载荷：

```json
{
  "version_id": "ip-version-uuid",
  "confirmed": true
}
```

### 已跳过 IP

```text
checkpoint = ip_choice
→ IPChoice(SKIP)
→ ip_skipped = true
→ generate_materials
→ 2 个 Material scenes
→ checkpoint = material_decision
```

恢复载荷：

```json
{"action": "SKIP"}
```

跳过路径不创建 IP Stage Version，也不调用 IP 文本/图片模型。

## 2. 建议业务 API

已生成 IP 的确认：

```http
POST /api/v1/stage-runs/{ip_run_id}/ip-confirmation
Content-Type: application/json
```

```json
{
  "version_id": "ip-version-uuid",
  "confirmed": true
}
```

跳过 IP 应复用上一阶段已经记录的 `IPChoice(SKIP)`，直接创建 Materials Run；不要为了“跳过”伪造一个空 IP Version。

## 3. Decision

### 已生成 IP

```text
stage: IP
action: CONFIRM_VERSION
source_version_id: IP Version ID
selected_item_id: null
resulting_stage_run_id: Materials Run ID
payload_json: {version_id, confirmed}
```

### 跳过 IP

沿用 VI→IP 交接中的选择记录：

```text
stage: IP
action: SELECT_OPTION
source_version_id: VI Version ID
selected_item_id: SKIP
resulting_stage_run_id: Materials Run ID
payload_json: {action: SKIP}
```

## 4. Materials Stage Run

```text
stage: MATERIALS
status: QUEUED
workflow_thread_id: 继承上游 Run
parent_stage_run_id:
  已生成 IP：IP Run ID
  跳过 IP：VI Run ID 或 IP Choice 业务 Run ID
```

已生成 IP 的 `input_json`：

```json
{
  "resume": {
    "version_id": "ip-version-uuid",
    "confirmed": true
  },
  "decision_id": "ip-confirm-decision-uuid",
  "ip_version_id": "ip-version-uuid",
  "vi_version_id": "vi-version-uuid"
}
```

跳过 IP 的 `input_json` 应继承此前保存的 SKIP resume 信息，并记录：

```text
ip_choice_decision_id
vi_version_id
ip_skipped: true
```

网页不能自行构造这些内部字段。

## 5. MaterialOutput

Materials 固定恰好 2 个场景：

```text
schema_version
scenes[2]
  id
  scenario_id
  name
  rationale
  used_asset_ids
  image_prompt
  preview_asset_id
```

每个 Scene 的引用规则：

### 已生成 IP

```text
used_asset_ids = [VI source Logo asset, IP preview asset]
```

### 跳过 IP

```text
used_asset_ids = [VI source Logo asset]
```

两个 Material `preview_asset_id` 必须唯一。

## 6. Worker 成功写入

Materials Run 成功后：

- 使用 `MaterialOutput` 校验 `result["material_output"]`。
- 创建不可变 Materials Stage Version。
- `input_refs_json` 记录 `vi_version_id`、可选 `ip_version_id`、上游 Decision ID 和 `ip_skipped`。
- 写入 2 个 Material Artifact。
- 写入 3 条模型调用记录：文本 1 条、图片 2 条。
- Stage Run 更新为 `SUCCEEDED`。
- Project `current_stage = MATERIALS`。
- checkpoint 为 `WAITING_USER / material_decision`。

## 7. 校验与幂等

已生成 IP：

1. IP Run 必须为 `SUCCEEDED`。
2. `version_id == ip_run.result_version_id`。
3. Version 属于相同 workspace/project，stage 为 `IP`。
4. `confirmed` 只能为 `true`。

跳过 IP：

1. 必须存在唯一的 `SELECT_OPTION / SKIP` Decision。
2. 不得存在 IP Stage Version。
3. 不得加载不存在的 `ip_output`。

相同请求重复提交返回原 Materials Run；不得重复生成 2 张物料图片。

## 8. 后端 1 验收

两条路径都必须满足：

```text
Materials Run：SUCCEEDED
Materials Stage Version：1
Material scenes：2
模型调用记录：3（文本 1 + 图片 2）
Material Artifacts：2
checkpoint：WAITING_USER / material_decision
```

附加要求：

- 已生成 IP：每个 scene 同时引用 Logo 和 IP。
- 跳过 IP：每个 scene 只引用 Logo，且 IP 调用/资产均为 0。
