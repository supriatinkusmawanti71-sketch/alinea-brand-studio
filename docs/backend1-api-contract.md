# Backend 1 API Contract

更新时间：2026-07-04

本文档记录后端 1 当前已经落库并可用于联调的项目、阶段版本和决策 API。业务数据以 PostgreSQL 为准；LangGraph checkpoint 只用于恢复 Agent 执行。

## Stage Keys

路径中的 `stage_key` 支持大小写不敏感的短横线/下划线写法，服务端会标准化为大写下划线：

```text
intake
directions
logo
vi
ip
materials
review
proposal
```

非法 stage key 返回：

```json
{"detail": "Invalid stage key: nope"}
```

HTTP 状态码为 `422`。

## Projects

### GET `/api/v1/dev/demo-flow`

开发环境共享假数据。返回体包含与项目恢复接口一致的 `project`、`brand_spec`、`current_stage`、`stage_runs`、`versions` 和 `decisions` 字段，供前后端联调时读取同一份示例契约。

为兼容 M0 早期消费者，当前仍保留旧的 `task` 和 `result` 字段；新联调优先使用项目状态字段。

### GET `/api/v1/dev/demo-completed-flow`

完成态项目的共享假数据。返回体与项目恢复接口一致，其中 `project.status=COMPLETED`、`current_stage=PROPOSAL`，可用于不跑真实数据库流程时验证完成态 UI。

### GET `/api/v1/dev/demo-proposal-manifest`

完成态 Proposal export manifest 的共享假数据。响应结构与正式接口：

```text
GET /api/v1/projects/{project_id}/exports/proposal-manifest
```

一致。

### GET `/api/v1/dev/demo-proposal.md`

完成态 Markdown 提案下载的共享假数据。响应为 `text/markdown; charset=utf-8`，带：

```text
Content-Disposition: attachment; filename="demo-proposal.md"
```

### GET `/api/v1/dev/demo-proposal.zip`

完成态 ZIP 交付包的共享假数据。响应为 `application/zip`，包内固定包含：

- `proposal.md`
- `proposal-manifest.json`

响应带：

```text
Content-Disposition: attachment; filename="demo-proposal.zip"
```

### POST `/api/v1/projects`

创建项目并排队首个 `INTAKE` StageRun。

请求体：

```json
{
  "name": "云山咖啡",
  "requirement_text": "做一个现代、克制的咖啡品牌。",
  "structured_fields": {
    "industry": "精品咖啡",
    "target_audiences": ["城市通勤者"]
  },
  "reference_artifact_ids": []
}
```

成功：`201`

```json
{
  "project": {
    "id": "project-uuid",
    "workspace_id": "local-workspace",
    "name": "云山咖啡",
    "current_stage": "INTAKE",
    "status": "ACTIVE",
    "version": 1
  },
  "stage_run": {
    "id": "run-uuid",
    "project_id": "project-uuid",
    "stage": "INTAKE",
    "status": "QUEUED",
    "attempt": 0,
    "error_code": null,
    "result_version_id": null
  }
}
```

失败：

- `422`：项目名为空或 `structured_fields` 包含不支持的 BrandSpec 字段。

### GET `/api/v1/projects`

返回当前 workspace 下项目列表，按 `updated_at desc` 排序。

### GET `/api/v1/projects/{project_id}`

返回项目详情、BrandSpec 和所有 StageRun 的简要信息。

失败：

- `404`：项目不存在或不属于当前 workspace。

### GET `/api/v1/projects/{project_id}/state`

页面刷新恢复接口。返回项目、BrandSpec、每个阶段最新 StageRun、每个阶段最新 StageVersion 和所有 Decision。

关键响应字段：

```json
{
  "project": {},
  "brand_spec": {},
  "current_stage": "LOGO",
  "stage_runs": {
    "DIRECTIONS": {"status": "SUCCEEDED"},
    "LOGO": {"status": "QUEUED"}
  },
  "versions": {
    "DIRECTIONS": {"status": "GENERATED"},
    "LOGO": {"status": "STALE"}
  },
  "decisions": []
}
```

`versions.*.status` 可能为：

- `GENERATED`：当前仍有效。
- `STALE`：上游阶段已有新选择，旧下游输出仅可作为历史版本展示。

失败：

- `404`：项目不存在或不属于当前 workspace。

## Stage Versions

### GET `/api/v1/projects/{project_id}/stages/{stage_key}/versions`

返回某项目某阶段的版本历史，按 `version_no desc` 排序。

成功：`200`

每个版本包含：

```json
{
  "id": "version-uuid",
  "project_id": "project-uuid",
  "stage_run_id": "run-uuid",
  "stage": "DIRECTIONS",
  "version_no": 1,
  "schema_version": 1,
  "input_refs": {},
  "output": {},
  "status": "GENERATED",
  "created_at": "2026-07-04T00:00:00Z"
}
```

失败：

- `404`：项目不存在或不属于当前 workspace。
- `422`：stage key 非法。

## Decisions

### POST `/api/v1/projects/{project_id}/stages/{stage_key}/decisions`

项目级阶段决策入口。当前 worker milestone 执行：

- `stage_key=directions` 的 `SELECT_VERSION`：选择一个 Directions 版本中的方向，并排队下一阶段 `LOGO` StageRun。
- `stage_key=logo` 的 `SELECT_VERSION`：选择一个 Logo 版本中的方案，并排队下一阶段 `VI` StageRun。
- `stage_key=vi` 的 `CONFIRM_VERSION`：确认一个 VI 版本，并排队下一阶段 `IP` StageRun；worker 执行后会停在 `ip_choice`，此时 `IP` StageRun 状态为 `WAITING_USER`，不会生成 IP StageVersion。
- `stage_key=ip` 的 `CONFIRM_VERSION`：确认一个已生成的 IP 版本，并排队下一阶段 `MATERIALS` StageRun。
- `stage_key=materials` 的 `CONFIRM_VERSION`：确认一个 Materials 版本，并排队下一阶段 `REVIEW` StageRun。
- `stage_key=review` 的 `CONFIRM_VERSION`：确认一个 Review 版本，并排队下一阶段 `PROPOSAL` StageRun。
- `stage_key=proposal` 的 `CONFIRM_VERSION`：确认最终 Proposal 版本，记录终态确认 StageRun，并将项目状态置为 `COMPLETED`；该动作不会派发 worker，也不会生成新的 StageVersion。

请求体：

```json
{
  "version_id": "directions-version-uuid",
  "selected_item_id": "direction-a",
  "action": "SELECT_VERSION"
}
```

确认类决策的请求体：

```json
{
  "version_id": "vi-version-uuid",
  "action": "CONFIRM_VERSION",
  "confirmed": true
}
```

成功：`202`

```json
{
  "decision": {
    "stage": "DIRECTIONS",
    "action": "SELECT_VERSION",
    "source_version_id": "directions-version-uuid",
    "selected_item_id": "direction-a",
    "resulting_stage_run_id": "logo-run-uuid"
  },
  "stage_run": {
    "id": "logo-run-uuid",
    "stage": "LOGO",
    "status": "QUEUED"
  }
}
```

Logo 选择成功时响应结构相同，其中 `decision.stage` 为 `LOGO`，`stage_run.stage` 为 `VI`。
VI 确认成功时响应结构相同，其中 `decision.stage` 为 `VI`，`stage_run.stage` 为 `IP`。
IP 确认成功时响应结构相同，其中 `decision.stage` 为 `IP`，`stage_run.stage` 为 `MATERIALS`。
Materials 确认成功时响应结构相同，其中 `decision.stage` 为 `MATERIALS`，`stage_run.stage` 为 `REVIEW`。
Review 确认成功时响应结构相同，其中 `decision.stage` 为 `REVIEW`，`stage_run.stage` 为 `PROPOSAL`。
Proposal 确认成功时响应结构相同，其中 `decision.stage` 为 `PROPOSAL`，`stage_run.stage` 为 `PROPOSAL`，`stage_run.status` 为 `SUCCEEDED`。

当前支持的 `action`：

- `SELECT_VERSION`：必须传 `selected_item_id`。当前 `directions` 和 `logo` 会真实排队下一阶段。
- `CONFIRM_VERSION`：必须传 `confirmed=true`。当前 `vi` 会真实排队到 `IP` 选择等待点，`ip` 会真实排队到 `MATERIALS`，`materials` 会真实排队到 `REVIEW`，`review` 会真实排队到 `PROPOSAL`，`proposal` 会真实完成项目。

幂等规则：

- 对同一个 `version_id` 和同一个 `selected_item_id` 重复提交，返回原 Decision 和原 StageRun，不重复派发 worker。
- 对同一个 `version_id` 提交不同 `selected_item_id`，返回 `409`。

下游过期规则：

- 创建新决策时，会将该阶段之后的已有 StageVersion 标记为 `STALE`。
- 例如重新选择 Directions 后，旧 Logo / VI / IP / Materials / Review / Proposal 版本会变为 `STALE`。
- 重新选择 Logo 后，旧 VI / IP / Materials / Review / Proposal 版本会变为 `STALE`。
- 重新确认 VI 后，旧 IP / Materials / Review / Proposal 版本会变为 `STALE`。
- 重新确认 IP 后，旧 Materials / Review / Proposal 版本会变为 `STALE`。
- 重新确认 Materials 后，旧 Review / Proposal 版本会变为 `STALE`。
- 重新确认 Review 后，旧 Proposal 版本会变为 `STALE`。
- 确认 Proposal 是终态动作，不会产生新的下游过期版本。

状态转换：

- 首次创建新的 `LOGO` StageRun 时，`project.current_stage` 会立即推进为 `LOGO`，即使 worker 仍处于 `QUEUED`。
- 首次创建新的 `VI` StageRun 时，`project.current_stage` 会立即推进为 `VI`，即使 worker 仍处于 `QUEUED`。
- 首次创建新的 `IP` StageRun 时，`project.current_stage` 会立即推进为 `IP`；worker 恢复到 IP 选择点后，该 StageRun 状态变为 `WAITING_USER`。
- 首次创建新的 `MATERIALS` StageRun 时，`project.current_stage` 会立即推进为 `MATERIALS`，即使 worker 仍处于 `QUEUED`。
- 首次创建新的 `REVIEW` StageRun 时，`project.current_stage` 会立即推进为 `REVIEW`，即使 worker 仍处于 `QUEUED`。
- 首次创建新的 `PROPOSAL` StageRun 时，`project.current_stage` 会立即推进为 `PROPOSAL`，即使 worker 仍处于 `QUEUED`。
- 确认 Proposal 后，`project.current_stage` 保持 `PROPOSAL`，`project.status` 变为 `COMPLETED`，最新 `PROPOSAL` StageRun 状态为 `SUCCEEDED` 且 `result_version_id` 指向被确认的 Proposal StageVersion。

失败：

- `404`：项目不存在，或版本不存在/不属于该项目。
- `422`：stage key 非法、action 非法，或 action 所需字段缺失。
- `409`：版本阶段与路径阶段不一致、版本已是 `STALE`、项目已完成但请求不是最终 Proposal 确认、选择项不存在、重复选择冲突，或当前 milestone 暂不支持该 stage。

当前限制：

- 项目已可完成到 `COMPLETED`，并支持 Markdown 提案下载；PDF / PPT 等二进制交付物尚未在本后端 1 milestone 内实现。

## Exports

### GET `/api/v1/projects/{project_id}/exports/proposal-manifest`

完成态项目的提案导出清单。该接口不生成文件、不拼 MinIO URL，只返回最终 Proposal 版本中的结构化提案内容和 asset ID，供后续文件导出/下载服务使用。

成功：`200`

```json
{
  "project_id": "project-uuid",
  "project_name": "云山咖啡",
  "proposal_version_id": "proposal-version-uuid",
  "proposal_stage_run_id": "proposal-run-uuid",
  "decision_id": "proposal-confirm-decision-uuid",
  "title": "云山咖啡 品牌概念提案",
  "narrative": "从品牌需求出发，形成方向、标识、规范与应用的一致叙事。",
  "sections": [
    {
      "type": "BRIEF",
      "title": "品牌简报",
      "summary": "用东方茶香提供轻盈的城市片刻。",
      "version_id": "directions-version-uuid",
      "asset_ids": []
    }
  ],
  "asset_refs": ["asset-uuid"],
  "generated_at": "2026-07-04T00:00:00Z"
}
```

失败：

- `404`：项目不存在或不属于当前 workspace。
- `409`：项目尚未 `COMPLETED`，或完成态项目缺少 Proposal 版本/最终确认决策。

### GET `/api/v1/projects/{project_id}/exports/proposal.md`

完成态项目的 Markdown 提案下载。内容由 Proposal export manifest 渲染得到，包含导出元数据、章节摘要、章节版本 ID、章节 asset ID 和全局 asset_refs。

成功：`200`

响应头：

```text
Content-Type: text/markdown; charset=utf-8
Content-Disposition: attachment; filename="proposal-{project_id}.md"
```

响应体示例：

```markdown
# 云山咖啡 品牌概念提案

从品牌需求出发，形成方向、标识、规范与应用的一致叙事。

## Export Metadata

- Project: 云山咖啡 (`project-uuid`)
- Proposal version: `proposal-version-uuid`
- Proposal stage run: `proposal-run-uuid`
- Final decision: `proposal-confirm-decision-uuid`
- Generated at: 2026-07-04T00:00:00+00:00

## Sections

### 品牌简报

- Type: `BRIEF`
- Version: `directions-version-uuid`
- Summary: 用东方茶香提供轻盈的城市片刻。
- Assets: none
```

失败：

- `404`：项目不存在或不属于当前 workspace。
- `409`：项目尚未 `COMPLETED`，或完成态项目缺少 Proposal 版本/最终确认决策。

### GET `/api/v1/projects/{project_id}/exports/proposal.zip`

完成态项目的 ZIP 交付包下载。当前包内固定包含：

- `proposal.md`：由最终 Proposal manifest 渲染的 Markdown 提案。
- `proposal-manifest.json`：与 `proposal-manifest` 接口一致的结构化导出清单。

成功：`200`

响应头：

```text
Content-Type: application/zip
Content-Disposition: attachment; filename="proposal-{project_id}.zip"
```

失败：

- `404`：项目不存在或不属于当前 workspace。
- `409`：项目尚未 `COMPLETED`，或完成态项目缺少 Proposal 版本/最终确认决策。

## Stage Controls

### POST `/api/v1/projects/{project_id}/stages/{stage_key}/redo`

### POST `/api/v1/projects/{project_id}/stages/{stage_key}/skip`

### POST `/api/v1/projects/{project_id}/stages/{stage_key}/generate`

当前 `intake/redo`、`directions/redo`、`ip/skip` 和 `ip/generate` 已执行真实状态转换：

- `intake/redo`：基于传入的 `INTAKE` StageVersion 创建新的 `INTAKE` StageRun，并派发 worker 重新执行 Intake。
- `directions/redo`：基于传入的 `DIRECTIONS` StageVersion 创建新的 `DIRECTIONS` StageRun，并派发 worker 重新生成方向。
- `ip/skip`：在 `IP` StageRun 处于 `WAITING_USER` 的 `ip_choice` 时，跳过 IP 并排队下一阶段 `MATERIALS` StageRun。
- `ip/generate`：在 `IP` StageRun 处于 `WAITING_USER` 的 `ip_choice` 时，生成 IP 并落库新的 `IP` StageVersion，随后等待 IP 确认。

其他 stage/action 当前仍只固化契约和错误语义，尚不执行真实状态转换。

请求体可省略，也可以传：

```json
{
  "source_version_id": "stage-version-uuid",
  "reason": "try another option"
}
```

当前行为：

- 校验 project / workspace / stage。
- 如果传入 `source_version_id`，会校验该版本存在、属于当前项目、且阶段与路径 `stage_key` 一致。
- `POST /api/v1/projects/{project_id}/stages/intake/redo` 必须传 `source_version_id`；成功后创建新的 `INTAKE` StageRun，记录 `Decision(stage=INTAKE, action=REDO)`，将旧 Intake 及下游版本标记为 `STALE`，并派发 worker。
- `POST /api/v1/projects/{project_id}/stages/directions/redo` 必须传 `source_version_id`；成功后创建新的 `DIRECTIONS` StageRun，记录 `Decision(stage=DIRECTIONS, action=REDO)`，将旧 Directions 及下游版本标记为 `STALE`，并派发 worker。
- `POST /api/v1/projects/{project_id}/stages/ip/skip` 不接受 `source_version_id`；它会查找当前项目最新的 `IP / WAITING_USER` StageRun。
- `ip/skip` 成功后创建 `MATERIALS` StageRun，记录 `Decision(stage=IP, action=SKIP)`，`source_version_id` 指向触发 IP 选择点的 VI 版本，并派发 worker。
- `POST /api/v1/projects/{project_id}/stages/ip/generate` 不接受 `source_version_id`；它会查找当前项目最新的 `IP / WAITING_USER` StageRun。
- `ip/generate` 成功后创建 `IP` StageRun，记录 `Decision(stage=IP, action=GENERATE)`，`source_version_id` 指向触发 IP 选择点的 VI 版本，并派发 worker。
- `ip/skip` 和 `ip/generate` 都要求触发 IP 选择点的 VI 版本仍为 `GENERATED`；如果上游已将该 VI 版本标记为 `STALE`，则不能继续推进旧 IP 选择。
- `ip/skip` 会将旧 IP / Materials / Review / Proposal 版本标记为 `STALE`。
- `ip/generate` 会将旧 IP / Materials / Review / Proposal 版本标记为 `STALE`；新生成的 IP 版本状态为 `GENERATED`。
- 如果项目已是 `COMPLETED`，所有 stage control 写操作都会返回 `409`，不创建 StageRun，不派发 worker。
- 其他 stage/action 校验通过后仍返回当前 milestone 未支持的 `409`，不创建 StageRun，不派发 worker。

失败：

- `404`：项目不存在或不属于当前 workspace。
- `404`：传入的 `source_version_id` 不存在或不属于当前项目。
- `422`：stage key 非法。
- `409`：传入的 `source_version_id` 阶段与路径阶段不一致。
- `409`：项目已是 `COMPLETED`，不再接受 stage control 写操作。
- `409`：`redo` 未传 `source_version_id`，或当前 stage 尚不支持真实 redo。
- `409`：`ip/skip` 没有找到等待中的 IP 选择点、传入了 `source_version_id`，或源 VI 版本已是 `STALE`。
- `409`：`ip/generate` 没有找到等待中的 IP 选择点、传入了 `source_version_id`，或源 VI 版本已是 `STALE`。
- `409`：当前 worker milestone 暂不支持该 stage/action。

## Legacy StageRun Entrypoints

### POST `/api/v1/stage-runs/{stage_run_id}/intake-answers`

旧入口，用于提交 Intake 补问答案并排队 `DIRECTIONS` StageRun。前端 1 仍可使用。

请求体：

```json
{
  "answers": [
    {
      "field_path": "industry",
      "value": "茶饮"
    }
  ]
}
```

成功：`202`

返回新建或已存在的 `DIRECTIONS` StageRun。

状态转换：

- 首次创建新的 `DIRECTIONS` StageRun 时，`project.current_stage` 会立即推进为 `DIRECTIONS`，即使 worker 仍处于 `QUEUED`。
- 首次创建新的 `DIRECTIONS` StageRun 时，会将 `INTAKE` 之后的已有 StageVersion 标记为 `STALE`，包括旧 Directions / Logo / VI / IP / Materials / Review / Proposal 版本。

幂等规则：

- 同一个 Intake StageRun 和完全相同的 answers 重复提交，返回原 `DIRECTIONS` StageRun，不重复派发 worker。

错误语义：

- `404`：StageRun 不存在或不属于当前 workspace。
- `409`：项目已是 `COMPLETED`，不再接受 Intake answers。
- `409`：StageRun 不是已成功的 `INTAKE`、Intake 没有可 resume 的结果，或 Intake 版本已是 `STALE`。

### POST `/api/v1/stage-runs/{stage_run_id}/direction-selection`

旧入口，用于选择方向并排队 `LOGO` StageRun。建议新联调优先使用项目级：

```text
POST /api/v1/projects/{project_id}/stages/directions/decisions
```

旧入口错误语义：

- `404`：StageRun 不存在或不属于当前 workspace。
- `409`：项目已是 `COMPLETED`，不再接受 Directions selection。
- `409`：StageRun 状态不允许选择、版本不匹配、Directions version 已是 `STALE`、选择项不存在或重复选择冲突。

### GET `/api/v1/stage-runs/{stage_run_id}`

返回 StageRun 详情和其 `result_version_id` 对应版本的 `output`。

失败：

- `404`：StageRun 不存在或不属于当前 workspace。

## Ownership Notes

- 后端 1 只返回 artifact ID 和版本输出，不拼 MinIO URL。
- 安全资产 URL / 短链由后端 3 storage adapter 提供。
- Logo 及之后阶段的真实 `redo`、PDF / PPT 等二进制导出仍待后续 milestone 对齐。
