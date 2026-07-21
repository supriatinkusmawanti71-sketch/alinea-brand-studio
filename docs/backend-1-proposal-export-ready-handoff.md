# 后端 1 接线交接：Proposal 确认 → Export Ready

更新时间：2026-07-04

## 1. Agent 最终恢复

```text
checkpoint = proposal_decision
→ ConfirmStageDecision
→ selected_version_ids.PROPOSAL 写入
→ LangGraph END
→ status = EXPORT_READY
```

恢复载荷：

```json
{
  "version_id": "proposal-version-uuid",
  "confirmed": true
}
```

此恢复不会调用任何文本/图片模型，也不会生成新 Artifact。

## 2. 建议业务 API

```http
POST /api/v1/stage-runs/{proposal_run_id}/proposal-confirmation
Content-Type: application/json
```

```json
{
  "version_id": "proposal-version-uuid",
  "confirmed": true
}
```

成功后业务状态进入 `EXPORT_READY`，并把后续文件任务交给后端 3。

## 3. 提交前校验

1. Proposal Run 属于当前 workspace/project。
2. `stage == PROPOSAL` 且 `status == SUCCEEDED`。
3. `version_id == proposal_run.result_version_id`。
4. Proposal Version 属于相同 project、stage 和 source run。
5. Proposal 引用的所有 Version 已确认且非 `STALE`。
6. `asset_refs` 指向的所有 Artifact 均存在、可读、非临时状态。
7. `confirmed` 只能为 `true`。

任一引用缺失、损坏、无权限或 `STALE` 时禁止进入导出。

## 4. Decision

```text
stage: PROPOSAL
action: CONFIRM_VERSION
source_version_id: Proposal Version ID
selected_item_id: null
resulting_stage_run_id: Export 编排 Run ID
created_by: 当前操作者
payload_json: {version_id, confirmed}
```

现有 `decisions.resulting_stage_run_id` 不允许为空，因此 Proposal 确认时应同时创建一个后端 3 可消费的 Export 编排 Run，而不是写入虚假的 Proposal Version。

## 5. Export 编排 Run

建议创建：

```text
stage: EXPORT
status: QUEUED
workflow_thread_id: 继承 Proposal Run
parent_stage_run_id: Proposal Run ID
idempotency_key: confirm-proposal:{proposal_version_id}
input_json:
  resume:
    version_id
    confirmed: true
  decision_id
  proposal_version_id
```

Export Run 首先完成 Agent 的最后一次 resume，得到 `EXPORT_READY`，然后由后端 3 分别创建 PDF、PPTX、ZIP 导出任务。

PDF、PPTX、ZIP 必须独立状态、独立失败重试；一个格式失败不能让其他格式一起失败。

## 6. 最终版本集合

跳过 IP：

```text
DIRECTIONS
LOGO
VI
MATERIALS
REVIEW
PROPOSAL
```

生成 IP：

```text
DIRECTIONS
LOGO
VI
IP
MATERIALS
REVIEW
PROPOSAL
```

该集合来自 checkpoint 执行上下文，只用于 Worker 校验。网页仍应通过 PostgreSQL 的 Version 和 Decision 关系读取已确认链路，不能直接读取 checkpoint。

## 7. Agent 完成后的业务写入

- Proposal Confirm Decision 已提交。
- Project `current_stage = EXPORT`。
- Project 保持 `ACTIVE`，直到所需导出任务完成。
- 不创建新的 Agent Stage Version。
- 不新增 Model Invocation。
- 不新增 Artifact。
- Export 编排 Run 可以标记 `SUCCEEDED`，其结果表示 `EXPORT_READY`。

项目只有在产品定义的必需导出全部成功后才进入 `DONE`。

## 8. 幂等

- 同一 Proposal Version 重复确认：返回原 Export 编排 Run。
- 不重复执行最终 checkpoint resume。
- 不重复创建 PDF/PPTX/ZIP 任务。
- 单个格式重试复用其自身幂等键，不重新确认 Proposal。

## 9. 后端 1 验收

```text
Proposal Confirm Decision：1
Export 编排 Run：1
Agent 最终状态：EXPORT_READY
新增 Stage Version：0
新增模型调用：0
新增 Artifact：0
```

必须覆盖：生成/跳过 IP 两条版本集合、`STALE` 上游、资产缺失、重复确认和 Worker 重建恢复。

文件生成、下载权限、签名 URL 和三种格式重试由后端 3负责。
