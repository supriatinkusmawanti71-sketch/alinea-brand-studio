# Docker And E2E Notes

Backend 3 owns Docker, Compose, Nginx, scripts, and E2E verification.

## Current Baseline

On the current `main` baseline, Dockerfiles still live under app folders:

- `apps/api/Dockerfile`
- `apps/web/Dockerfile`

The M0 integration branch is expected to move Dockerfiles under `infra/docker/`.
After M0 is merged, re-check these paths before changing Compose.

## Local Commands

Check the environment:

```sh
./scripts/check-environment.sh
```

Start the stack:

```sh
docker compose up --build -d
```

Verify the stack:

```sh
./scripts/verify-stack.sh
```

Run E2E smoke:

```sh
./scripts/run-e2e.sh
```

Stop the stack:

```sh
docker compose stop
```

## E2E Behavior

E2E tests are skipped by default. They run only when:

```sh
BRAND_STUDIO_RUN_E2E=1 .venv/bin/python -m pytest tests/e2e
```

Prefer `./scripts/run-e2e.sh` because it starts, verifies, tests, and stops the stack.

## M0 Merge Reminder

Do not make broad Compose or Docker path changes until M0 is merged.

After M0:

1. Pull latest `main`.
2. Rebase Backend 3 branch.
3. Check Dockerfile paths in `compose.yaml`.
4. Rerun `./scripts/run-e2e.sh`.
