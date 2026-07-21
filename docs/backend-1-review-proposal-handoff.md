# 后端 1 接线交接：Review 决策 → Proposal 决策点

更新时间：2026-07-04

## 1. Agent 流程

```text
checkpoint = review_decision
→ ReviewDecision
→ generate_proposal
→ ProposalOutput
→ checkpoint = proposal_decision
```

恢复载荷：

```json
{
  "version_id": "review-version-uuid",
  "proceed": true,
  "accepted_issue_ids": []
}
```

Agent Schema：

```text
ReviewDecision
  version_id: UUID
  proceed: 只能为 true
  accepted_issue_ids: string[]，最多 50 个
```

## 2. 建议业务 API

```http
POST /api/v1/stage-runs/{review_run_id}/review-decision
Content-Type: application/json
```

成功后返回新的 Proposal Run，网页继续轮询该 Run。

## 3. 业务层必须先校验

1. Review Run 属于当前 workspace/project。
2. `stage == REVIEW` 且 `status == SUCCEEDED`。
3. `version_id == review_run.result_version_id`。
4. Review Version 属于相同 project、stage 和 source run。
5. `accepted_issue_ids` 是当前 Review `issues[*].id` 的子集。
6. 所有上游引用 Version 均为已确认且非 `STALE`。

以下类别不能通过 `accepted_issue_ids` 绕过：

```text
SECURITY
PERMISSION
MISSING_ASSET
CORRUPTED_FILE
```

普通品牌一致性、颜色、字体等 Warning 可以由用户明确接受风险。强制规则必须在后端校验，不能只隐藏前端按钮。

## 4. Decision

为了让同一 Review Version 只有一条继续决定，建议统一使用：

```text
stage: REVIEW
action: ACCEPT_RISK
source_version_id: Review Version ID
selected_item_id: null
resulting_stage_run_id: Proposal Run ID
payload_json:
  version_id
  proceed
  accepted_issue_ids
```

即使 `accepted_issue_ids` 为空也使用同一个 action，避免 `CONFIRM_VERSION` 和 `ACCEPT_RISK` 两种 action 绕过现有唯一约束生成两个 Proposal Run。

## 5. Proposal Stage Run

```text
stage: PROPOSAL
status: QUEUED
workflow_thread_id: 继承 Review Run
parent_stage_run_id: Review Run ID
idempotency_key: proceed-review:{review_version_id}
```

内部 `input_json`：

```json
{
  "resume": {
    "version_id": "review-version-uuid",
    "proceed": true,
    "accepted_issue_ids": []
  },
  "decision_id": "review-decision-uuid",
  "review_version_id": "review-version-uuid"
}
```

## 6. ProposalOutput 固定结构

正式字段：

```text
schema_version
title
narrative
sections[6..7]
  type
  title
  summary
  version_id
  asset_ids[]
asset_refs[]
```

跳过 IP 时固定 6 节：

```text
BRIEF
DIRECTION
LOGO
VI
MATERIALS
REVIEW_SUMMARY
```

生成 IP 时固定 7 节：

```text
BRIEF
DIRECTION
LOGO
VI
IP
MATERIALS
REVIEW_SUMMARY
```

版本引用：

- BRIEF、DIRECTION → Directions Version。
- LOGO → Logo Version。
- VI → VI Version。
- IP → IP Version，仅生成 IP 时存在。
- MATERIALS → Materials Version。
- REVIEW_SUMMARY → Review Version。

资产引用：

- 选中的 Direction preview。
- 选中的 Logo preview。
- 可选 IP preview。
- 两个 Materials preview。
- `asset_refs` 必须唯一。

Proposal 不能引用旧版本、未确认版本或 `STALE` 版本。

## 7. Worker 成功写入

Proposal Run 成功后：

- 使用 `ProposalOutput` 校验 `result["proposal_output"]`。
- 创建不可变 Proposal Stage Version。
- `input_refs_json` 记录所有实际引用的 Version ID 和 Review Decision ID。
- 写入 1 条 Proposal 文本模型调用记录。
- 不创建新 Artifact。
- Stage Run 更新为 `SUCCEEDED`。
- Project `current_stage = PROPOSAL`。
- checkpoint 为 `WAITING_USER / proposal_decision`。

## 8. 幂等

- 相同 Review Version 和相同 `accepted_issue_ids` 重提：返回原 Proposal Run。
- 同一 Review Version 修改已接受风险集合：返回 HTTP 409；不能再次恢复同一 checkpoint。
- Proposal 生成失败按原 Stage Run 重试，不创建第二条 Review Decision。

## 9. 后端 1 验收

```text
Review Decision：1
Proposal Run：SUCCEEDED
Proposal Stage Version：1
Proposal 模型调用：1 条文本
新增 Artifact：0
checkpoint：WAITING_USER / proposal_decision
```

必须覆盖：禁止绕过类别、accepted_issue_ids 非法、上游 `STALE`、IP 包含/排除、重复提交幂等，以及 Worker 重建恢复。
