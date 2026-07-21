# 后端 1 接线交接：VI 确认 → IP 生成或跳过

更新时间：2026-07-04

## 1. Agent 的连续中断事实

这一步包含两个不同的人工输入，必须按顺序 resume：

```text
vi_decision
→ ConfirmStageDecision
→ ip_choice
→ IPChoice(GENERATE | SKIP)
```

不能把下面两个 JSON 合并后只调用一次 `Command`。

第一次恢复：

```json
{
  "version_id": "vi-version-uuid",
  "confirmed": true
}
```

第二次恢复：

```json
{"action": "GENERATE"}
```

或：

```json
{"action": "SKIP"}
```

正式 Agent Schema：

```text
ConfirmStageDecision
  version_id: UUID
  confirmed: 只能为 true

IPChoice
  action: GENERATE | SKIP
```

## 2. 两条分支的结果

### GENERATE

```text
IPChoice(GENERATE)
→ 1 次 IP 文本模型调用
→ 1 次图片模型调用
→ 1 个 IPOutput
→ checkpoint 停在 ip_decision
```

`IPOutput`：

```text
schema_version
character
  name
  role
  personality[2..8]
  appearance
  brand_connection
pose
  name
  description
image_prompt
preview_asset_id
```

生成图片必须引用 `VIOutput.source_logo_asset_id`。

### SKIP

```text
IPChoice(SKIP)
→ 不调用 IP 文本或图片模型
→ ip_skipped = true
→ status = MATERIALS
→ 当前完整 Graph 会继续生成 Materials
→ checkpoint 停在 material_decision
```

业务层如果需要把“跳过 IP”和“生成 Materials”拆成两张任务卡，可以为 SKIP 的 Worker 构建 Graph 时在 `generate_materials` 前设置静态暂停，再由新的 Materials Run 继续。

## 3. 推荐的 MVP 业务请求

由于 Graph 有连续两个中断点，而现有 Stage Run 状态没有单独的 `IP_CHOICE` 运行状态，MVP 推荐让网页在确认 VI 时同时选择 IP 行为：

```http
POST /api/v1/stage-runs/{vi_run_id}/vi-confirmation
Content-Type: application/json
```

```json
{
  "version_id": "vi-version-uuid",
  "confirmed": true,
  "ip_action": "GENERATE"
}
```

Worker 内仍需顺序调用两次：

```python
workflow.invoke(Command(resume=vi_confirmation), config=config)
workflow.invoke(Command(resume={"action": ip_action}), config=config)
```

不要将两个 payload 合并传给同一个 `Command`。

如果产品决定让用户分两个页面操作，后端 1 必须为第一次恢复设计 PostgreSQL 可见的中间业务状态；页面不能读取 checkpoint 判断当前处于 `ip_choice`。

## 4. Decision 建议

复用同一张 `decisions` 表：

### VI 确认

```text
stage: VI
action: CONFIRM_VERSION
source_version_id: VI Version ID
selected_item_id: null
payload_json: {version_id, confirmed}
```

### IP 选择

建议为业务动作增加统一的 `SELECT_OPTION`：

```text
stage: IP
action: SELECT_OPTION
source_version_id: 同一个 VI Version ID
selected_item_id: GENERATE | SKIP
payload_json: {action}
```

使用相同 `action=SELECT_OPTION` 可以让现有 `source_version_id + action` 唯一约束阻止同一 VI Version 同时出现 GENERATE 和 SKIP。

不要分别使用 `GENERATE_STAGE` 和 `SKIP_STAGE` 作为两个不同 action；现有唯一约束无法阻止两条冲突记录同时存在。

## 5. Stage Run 建议

### GENERATE

创建 IP Run：

```text
stage: IP
workflow_thread_id: 继承 VI Run
parent_stage_run_id: VI Run ID
input_json:
  resume_sequence:
    - {version_id, confirmed: true}
    - {action: GENERATE}
  vi_decision_id
  ip_choice_decision_id
  vi_version_id
```

成功后创建 IP Stage Version，项目 `current_stage = IP`。

### SKIP

不创建 IP Stage Version。将 IP 业务阶段记录为 `SKIPPED`，然后创建 Materials Run：

```text
stage: MATERIALS
workflow_thread_id: 继承 VI Run
parent_stage_run_id: VI Run ID
input_json:
  resume_sequence:
    - {version_id, confirmed: true}
    - {action: SKIP}
  vi_decision_id
  ip_choice_decision_id
  vi_version_id
```

## 6. 幂等与校验

必须校验：

1. VI Run 为 `SUCCEEDED`。
2. `version_id == vi_run.result_version_id`。
3. Version 属于相同 workspace/project，且 stage 为 `VI`。
4. `confirmed` 只能为 `true`。
5. `ip_action` 只能为 `GENERATE` 或 `SKIP`。

幂等：

- 同一 VI Version 重复提交相同选择：返回原后续 Run。
- 同一 VI Version 已选 GENERATE 后再选 SKIP：HTTP 409。
- GENERATE 和 SKIP 都不能重复恢复相同 checkpoint。

## 7. 后端 1 验收

### GENERATE

```text
VI Confirm Decision：1
IP Choice Decision：1
IP Run：SUCCEEDED
IP Stage Version：1
IP 模型调用记录：2（文本 1 + 图片 1）
IP Artifact：1
checkpoint：WAITING_USER / ip_decision
```

### SKIP

```text
VI Confirm Decision：1
IP Choice Decision：1
IP Stage：SKIPPED
IP Stage Version：0
IP 模型调用：0
IP Artifact：0
后续进入 MATERIALS
```
