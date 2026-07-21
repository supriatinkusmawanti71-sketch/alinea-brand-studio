# 五人团队开工计划

当前配置：2 名前端、3 名后端；产品负责人负责需求决策、优先级和最终验收。

## 角色边界

### 前端 1：项目与需求流程

- 首页、项目列表、新建项目和项目详情骨架。
- BrandSpec 表单、Intake 补问和答案提交。
- 通用 API Client、任务轮询、错误/空/加载状态。
- 维护 `features/projects`、`features/intake`、`lib/api` 和通用 UI。

### 前端 2：品牌生成工作台

- 阶段导航和生成、待选择、完成状态。
- Directions、Logo、VI、IP、物料、审稿、提案和导出界面。
- 提交 Version ID 与 Item ID，展示安全资产 URL。
- 维护 `features/workbench`、`features/directions`、`features/logo` 和 `features/deliverables`。

### 后端 1：业务 API、数据库和状态

- Project、BrandSpec、Stage Run、Stage Version、Decision 和 Outbox。
- 各阶段选择、确认、跳过和重做 API。
- 归属校验、幂等、状态转换、下游 `STALE` 和 OpenAPI。
- 维护 `apps/api/app/routers`、`backend/application`、数据库模型与迁移。

### 后端 2：Agent 与模型流程

- Agent Schema、Prompt、LangGraph 和 checkpoint 恢复载荷。
- Fake Provider、硅基流动 Provider 和模型错误处理。
- 逐阶段推进 VI、IP、Materials、Review 和 Proposal。
- 维护 `backend/agents`、`backend/providers` 及对应 Agent 测试。

### 后端 3：资产、导出、环境与质量

- MinIO/S3 上传、短期 URL 和临时资产清理。
- PDF、PPTX、ZIP 导出任务。
- Docker Compose、Nginx、CI、部署检查和真实 E2E。
- 维护 Storage、Export、`infra`、`scripts`、`.github` 和 E2E 测试。

## 第一轮任务

第一轮只让页面真实走完“创建项目 → Intake → Directions → 选择方向 → Logo”。

| 负责人 | 第一张任务卡 | 验收结果 |
|---|---|---|
| 前端 1 | 项目创建、Intake、任务轮询 | 提交答案并拿到 Directions Run |
| 前端 2 | Directions/Logo 工作台 | 选择方向并展示 3 个 Logo |
| 后端 1 | 固化 API/OpenAPI 和项目恢复字段 | 刷新后从 PostgreSQL API 恢复页面 |
| 后端 2 | Logo 选择 → VI 决策点 | checkpoint 停在 `vi_decision` |
| 后端 3 | 资产短期 URL 和基础 CI | 前端通过 artifact ID 显示图片 |

## 协作规则

- PostgreSQL 业务表是页面唯一真相，checkpoint 只用于恢复执行。
- 前端统一使用 OpenAPI/共享契约，不手写第二套 DTO。
- 后端 3 不另建 Artifact 表，不返回永久公开 URL。
- 每张任务卡只跨越一个人工决策点。
- API/Schema 改动必须同时更新契约、测试和文档。
- 每个人从最新 `main` 创建自己的功能分支，不直接提交 `main`。
- 提交前运行 `make check`，在 PR 中填写实际结果。

## 环境要求

所有人必装 Git、Docker Desktop、代码编辑器，并取得仓库权限。Docker 模式不需要单独安装 Node、Python、PostgreSQL、Redis 或 MinIO。

首次启动：

```bash
cp .env.example .env
./scripts/check-environment.sh
docker compose up --build
```

脱离 Docker 时，前端使用 Node.js 22，后端使用 Python 3.12 和 `uv`。本地统一使用 Fake Provider，不需要真实模型密钥。
