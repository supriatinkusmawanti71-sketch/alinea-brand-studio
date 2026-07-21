# Aline Brand Workbench

品牌 Agent 项目的共同开发仓库。当前目标是在约 7 天内先跑通完整逻辑，默认使用假 AI，不追求生成和页面效果。

原有视觉原型保存在 `prototypes/legacy/index.html`。正式网页代码放在 `apps/web/`。

当前 2 名前端、3 名后端的职责和第一轮任务见 [`docs/team-plan.md`](docs/team-plan.md)。

## 所有人先安装

必装：

1. Git
2. Docker Desktop（打开后确保 Docker 正在运行）
3. 任意 AI Coding 工具：Codex、Cursor、Claude Code 等

默认使用 Docker 时，不需要单独安装 PostgreSQL、Redis、MinIO、Node.js 或 Python。

如果希望脱离 Docker 本地运行，再额外安装：

- Node.js 22
- Python 3.12
- uv

检查共同环境：

```bash
./scripts/check-environment.sh
```

## 第一次启动

```bash
git clone https://github.com/xiaoyangqiqi7777777/aline-brand-workbench.git
cd aline-brand-workbench
cp .env.example .env
docker compose up --build
```

服务全部健康后访问：

| 服务 | 地址 | 用途 |
|---|---|---|
| 统一入口 | http://localhost:8080 | 所有人优先使用这个地址 |
| Next.js 网页 | http://localhost:3000 | 前端直接调试 |
| FastAPI 文档 | http://localhost:8000/api/docs | 查看和测试后端接口 |
| API 健康检查 | http://localhost:8000/api/v1/health/ready | 检查数据库和 Redis |
| MinIO 控制台 | http://localhost:9001 | 查看本地上传文件 |
| PostgreSQL | 127.0.0.1:5432 | 本地数据库，仅绑定本机 |
| Redis | 127.0.0.1:6379 | 本地任务队列，仅绑定本机 |

MinIO 本地账号来自 `.env`：

- 用户名：`brand-agent-local`
- 密码：`brand-agent-local-secret`

这些只用于本地开发，线上必须更换。

## 常用命令

```bash
make dev       # 启动全部服务
make down      # 停止服务
make logs      # 查看日志
make ps        # 查看服务状态
make check     # 提交代码前的全部检查
make clean     # 删除容器和本地开发数据
```

直接使用 Docker Compose 也可以：

```bash
docker compose up --build
docker compose down
docker compose logs -f --tail=200
```

## 不使用 Docker 的本地启动方式

```bash
cp .env.example .env
npm install
uv sync

npm run dev:web
uv run uvicorn apps.api.app.main:app --reload --port 8000
uv run celery -A apps.api.app.celery_app.celery_app worker --loglevel=INFO
```

本地直接运行 API 时，需要把 `.env` 中的 `postgres`、`redis`、`minio` 主机名改为 `localhost`，数据库等基础服务仍可通过 Docker 启动。

## 团队统一约定

- 默认 `TEXT_MODEL_PROVIDER=fake`、`IMAGE_MODEL_PROVIDER=fake`，不要自行加入真实密钥。
- 真实 Agent 联调时，把两个 provider 都切到 `siliconflow`，并在私有 `.env` 中配置 `SILICONFLOW_API_KEY`、`TEXT_MODEL_NAME`、`IMAGE_MODEL_NAME`。
- OpenRouter 测试联调时，把两个 provider 都切到 `openrouter`，在私有 `.env` 中配置 `OPENROUTER_API_KEY`，默认文本模型可用 `bytedance-seed/seed-2.0-mini`，默认图片模型可用 `bytedance-seed/seedream-4.5`，Seedream 图片尺寸用 `OPENROUTER_IMAGE_SIZE=2048x2048`。
- OpenAI 联调时，把两个 provider 都切到 `openai`，在私有 `.env` 中配置 `OPENAI_API_KEY`；默认文本模型可用 `gpt-4.1-mini`，默认图片模型可用 `gpt-image-2`。
- 三 Agent 可单独覆盖模型：`SILICONFLOW_*`、`OPENROUTER_*` 或 `OPENAI_*` 的 `ART_DIRECTOR_TEXT_MODEL`、`LOGO_AGENT_TEXT_MODEL`、`IP_DESIGNER_TEXT_MODEL`；图片模型可用 `DIRECTIONS_IMAGE_MODEL`、`LOGO_IMAGE_MODEL`、`IP_IMAGE_MODEL` 覆盖。
- 每个人从最新 `main` 创建自己的功能分支，不直接修改 `main`。
- `.env`、模型密钥、数据库密码禁止提交 Git。
- 公共假数据放在 `contracts/examples/`，不要在每个模块复制一份。
- 接口字段由后端负责人确认；前端从 OpenAPI 或共享契约读取。
- 提交前运行 `make check`，把实际结果写进 PR。
- 端口冲突时只修改自己本机 `.env`，不要修改公共默认值。

## 项目结构

```text
apps/web/            Next.js 网页
apps/api/            FastAPI 和 Celery Worker
contracts/examples/  全团队共用的假数据
infra/docker/        Web/API 镜像
infra/nginx/         统一入口
tests/               后端和流程测试
compose.yaml         一键启动全部服务
prototypes/legacy/  原始视觉原型
```

## 环境出现问题时

```bash
docker compose ps
docker compose logs api --tail=200
docker compose logs web --tail=200
docker compose logs worker --tail=200
```

仍无法启动时，把以下内容发给后端 3（环境负责人）：操作系统、`docker compose ps` 输出、失败服务日志，以及自己是否修改过 `.env`。
