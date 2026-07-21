# Backend 2 Main-Ready Handoff

更新时间：2026-07-05

## 目的

旧 `codex/backend2-finalization` 从过期基线逐步堆叠，直接合入最新 `main` 会带入大量无关基线差异，而且原 PR 已关闭、父分支已删除。

本分支 `codex/backend2-main-ready` 从最新 `origin/main@7b2c81f` 创建，只保留后端 2 尚未进入主线的阶段恢复测试和后端 1 对接文档，可直接作为新的 Backend 2 PR 来源。

## 已整理的增量

依次移植：

```text
e5c7a68 Logo → VI checkpoint resume
69ea578 VI → IP choice checkpoint resume
c85f0c5 IP → Materials checkpoint resume
95e451d Materials → Review checkpoint resume
1fa587c Review → Proposal checkpoint resume
98abc18 Proposal confirmation → Export Ready
```

未移植旧 M0 集成提交 `4fc78e7`，因为 Agent 核心和共享基线已经存在于最新 `main`。

## 分支内容

- `tests/backend/agents/test_workflow.py`：增加 544 行分阶段 checkpoint 恢复测试。
- `docs/backend-1-logo-vi-handoff.md`
- `docs/backend-1-vi-ip-handoff.md`
- `docs/backend-1-ip-materials-handoff.md`
- `docs/backend-1-materials-review-handoff.md`
- `docs/backend-1-review-proposal-handoff.md`
- `docs/backend-1-proposal-export-ready-handoff.md`

本次整理没有修改：

- GitHub Actions 和 CI 配置。
- FastAPI Router、后端 1 业务代码和数据库迁移。
- 前端页面、依赖与锁文件。
- Docker Compose 和环境基线。
- 已存在的其他成员分支。

## 验证结果

执行：

```bash
npm ci --prefer-offline --no-audit --no-fund
uv sync
make check
git diff --check origin/main...HEAD
```

结果：

- Ruff：通过。
- Ruff format：70 个文件格式正确。
- ESLint：通过。
- TypeScript：通过。
- Python：`140 passed`。
- Web contract test：`1 passed`。
- Next.js production build：通过。
- 仅有 FastAPI TestClient 的第三方弃用警告，不影响功能。

## GitHub 交付建议

将本分支推送为新远端分支，并建立：

```text
codex/backend2-main-ready → main
```

新的 PR 应替代已关闭的后端 2 堆叠 PR，不应重新打开旧 PR，也不应直接合并旧 `codex/backend2-finalization`。
