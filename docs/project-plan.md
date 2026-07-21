# Alinea 项目规划

个人全栈项目。开发策略:先以 Fake Provider 零成本跑通端到端流程,固化接口契约与状态机,再接入真实模型打磨生成质量,最后做界面升级。

## 模块划分

按工作域拆分为五块,对应仓库目录:

### 前端 · 项目与需求流程

- 首页、项目列表、新建项目和项目详情骨架。
- BrandSpec 表单、Intake 补问和答案提交。
- 通用 API Client、任务轮询、错误/空/加载状态。
- 代码位置:`features/projects`、`features/intake`、`lib/api` 和通用 UI。

### 前端 · 品牌生成工作台

- 阶段导航和生成、待选择、完成状态。
- Directions、Logo、IP 与导出界面。
- 提交 Version ID 与 Item ID,展示安全资产 URL。
- 代码位置:`features/workbench`、`features/directions`、`features/logo`。

### 后端 · 业务 API、数据库和状态

- Project、BrandSpec、Stage Run、Stage Version、Decision 和 Outbox。
- 各阶段选择、确认、跳过和重做 API。
- 归属校验、幂等、状态转换、下游 `STALE` 和 OpenAPI。
- 代码位置:`apps/api/app/routers`、`backend/application`、数据库模型与迁移。

### 后端 · Agent 与模型流程

- Agent Schema、Prompt、LangGraph 编排和 checkpoint 恢复载荷。
- Fake / SiliconFlow / OpenRouter / OpenAI 四种 Provider 与模型错误处理。
- 代码位置:`backend/agents`、`backend/providers` 及对应 Agent 测试。

### 后端 · 资产、导出、环境与质量

- MinIO/S3 上传、短期 URL 和临时资产清理。
- 交付包导出任务。
- Docker Compose、Nginx、CI、部署检查和 E2E。
- 代码位置:Storage、Export、`infra`、`scripts`、`.github` 和 E2E 测试。

## 里程碑

已完成:

| 里程碑 | 内容 | 验收标准 |
|---|---|---|
| M1 端到端流程 | 创建项目 → Intake → Directions → 选择方向 → Logo → IP → 确认 → 下载 ZIP,全程 Fake Provider | 提交答案拿到 Directions Run;选择方向后生成 Logo;刷新后从 PostgreSQL 恢复页面;checkpoint 停在人工决策点;资产以短期 URL 展示 |
| M2 真实模型接入 | Provider 抽象层接入 SiliconFlow / OpenRouter / OpenAI,支持按 Agent 覆盖模型 | 仅改 `.env` 即可在四种供应商间切换,业务代码零改动 |
| M3 界面改版 | 设计 token 统一至 `:root`,整体换肤「纸墨画廊」,产品更名 Alinea | 全部颜色经 token 引用;类名契约与轮询逻辑不受影响 |

规划中:

- VI、物料、审稿、提案四个阶段接入主流程(Schema 已就绪,见 `backend/agents/schemas/`)。
- PDF、PPTX 导出。
- 业务级浏览器 E2E(当前 E2E 仅覆盖基础设施冒烟)。
- 首页错误展示与 STALE 状态提示的体验补强。

## 工程规则

- PostgreSQL 业务表是页面唯一真相,checkpoint 只用于恢复执行。
- 前端统一使用 OpenAPI/共享契约,不手写第二套 DTO。
- 不建永久公开资产 URL,一律短期签名 URL。
- 每个任务只跨越一个人工决策点。
- API/Schema 改动必须同时更新契约、测试和文档。
- 功能分支开发,`main` 保持随时可运行;合并前运行 `make check`。

## 环境要求

必装 Git、Docker Desktop、代码编辑器。Docker 模式不需要单独安装 Node、Python、PostgreSQL、Redis 或 MinIO。

首次启动:

```bash
cp .env.example .env
./scripts/check-environment.sh
docker compose up --build
```

脱离 Docker 时,前端使用 Node.js 22,后端使用 Python 3.12 和 `uv`。本地默认使用 Fake Provider,不需要真实模型密钥。
