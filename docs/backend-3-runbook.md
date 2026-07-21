# Backend 3 Runbook

Owner scope: artifact storage, exports, Docker/Compose, Nginx, scripts, E2E, deployment notes.

This runbook intentionally avoids business Router, database migrations, and project state fields. Those belong to Backend 1.

## Current PR

- Branch: `feat/backend-3-artifact-access`
- PR: Backend 3 artifact storage, export services, scripts, and E2E
- Status target before review: CI green, M0 merged into `main`, then rebase this branch

## Local Setup

```sh
cp .env.example .env
./scripts/check-environment.sh
```

Expected result:

```text
环境检查通过，可以执行：docker compose up --build
```

## Start And Verify Stack

```sh
docker compose up --build -d
./scripts/verify-stack.sh
```

The verification script checks:

- Docker and Docker Compose are available.
- Long-running services are running and healthy:
  - `postgres`
  - `redis`
  - `minio`
  - `api`
  - `worker`
  - `web`
  - `nginx` or `gateway`
- Health endpoints respond:
  - Gateway `/health`
  - Web `/api/health`
  - API `/api/v1/health/ready`
  - API docs `/api/docs`
  - MinIO `/minio/health/live`
  - MinIO console

Stop services:

```sh
docker compose stop
```

## Run E2E

```sh
./scripts/run-e2e.sh
```

This script:

1. Creates `.env` from `.env.example` when missing.
2. Builds and starts Docker Compose.
3. Runs `./scripts/verify-stack.sh`.
4. Runs `BRAND_STUDIO_RUN_E2E=1 .venv/bin/python -m pytest tests/e2e`.
5. Stops Docker Compose automatically.

Keep services running after E2E:

```sh
KEEP_STACK=1 ./scripts/run-e2e.sh
```

Use another Python executable:

```sh
E2E_PYTHON=python3 ./scripts/run-e2e.sh
```

## Artifact Storage Service

Implemented in `backend/infrastructure/storage/`.

Available service methods:

- `put_artifact(upload)`
- `ensure_artifact_exists(reference)`
- `create_download_url(reference, expires_in_seconds=None)`
- `delete_artifact(reference)`
- `delete_artifacts_by_prefix(bucket, prefix, older_than=None, batch_size=1000)`

Backend 1 needs to provide these fields from the business database before calling Backend 3 services:

- `artifact_id`
- `bucket`
- `object_key`
- `filename`
- `content_type`

Frontend should receive short-lived URLs only. Persistent image/file references should use artifact IDs.

Object key helpers are exported from `backend.infrastructure.storage`:

- `build_artifact_object_key(project_id, stage, artifact_id, filename)`
- `build_prefixed_artifact_object_key(prefix, artifact_id, filename)`
- `build_temporary_artifact_prefix(project_id, scope=None)`
- `FileArtifactService.store_file(request)`
- `create_asset_url_map(storage, references, expires_in_seconds=None)`
- `create_presigned_url_map(storage, references, expires_in_seconds=None)`

Current Frontend 1 branch (`feat/frontend-1-project-intake`) creates projects with
`reference_artifact_ids`. The future `POST /files` Router should:

1. Read the uploaded file bytes.
2. Call `FileArtifactService.store_file()` with `stage="references"`.
3. Persist the returned `artifact_id`, `bucket`, `object_key`, `filename`, `content_type`
   as `mime_type`, `size_bytes`, and `sha256` in Backend 1's artifact table.
4. Return the stored `artifact_id` so Frontend 1 can include it in `reference_artifact_ids`.

Current Frontend 2 branch (`qianduan2`) expects result payloads to carry `preview_asset_id`
and a separate `assetUrls` map keyed by artifact ID. Backend 1 should resolve those artifact IDs
from the database and call `create_asset_url_map()` before returning UI-facing result data.

## Export Service

Implemented in `backend/exports/`.

Available service methods:

- `ExportRenderer.render(request)`
- `ExportArtifactService.render_and_store(request, target)`

Supported formats:

- `pdf`
- `pptx`
- `zip`

Current `main` already lets the agent workflow reach `status = EXPORT_READY` after Proposal
confirmation. The Backend 2 finalization handoff expects Backend 1 to create a durable Export
orchestration run, then call Backend 3 for file generation.

Expected handoff into Backend 3:

1. Backend 1 validates the confirmed Proposal version, confirmed upstream version chain, and
   artifact readability.
2. Backend 1 creates an export orchestration record/run with an idempotency key based on the
   Proposal version.
3. Backend 1 builds an `ExportRequest` from PostgreSQL stage versions and selected artifact refs.
4. Backend 1 calls `ExportArtifactService.render_and_store()` once per required format.
5. Backend 1 persists each returned export artifact independently.

Each export format must have its own status and retry path. PDF, PPTX, and ZIP failures should not
fail or retry the other formats together.

Backend 1 still needs to define:

- `POST /exports` request fields
- Export orchestration run/table shape after `EXPORT_READY`
- Export task table or persistence model
- Export status query shape
- Artifact lookup flow
- Transaction boundaries

Frontend 2 still needs to confirm:

- Which stages expose export buttons
- Which formats are shown for each stage
- Download/status UI behavior
- Whether preview assets are returned as `assetUrls` on every workbench payload or by a separate
  artifact URL endpoint

## Common Failures

### Port Is Already In Use

Run:

```sh
docker ps
lsof -nP -iTCP:3000 -sTCP:LISTEN
```

Stop the Compose stack if it belongs to this project:

```sh
docker compose stop
```

### Docker Desktop Is Not Running

Start Docker Desktop, then run:

```sh
docker info
./scripts/check-environment.sh
```

### MinIO Bucket Or Object Storage Fails

Check:

```sh
docker compose ps minio minio-init
curl -f http://127.0.0.1:9000/minio/health/live
```

Then rerun:

```sh
./scripts/verify-stack.sh
```

### Worker Stays In Starting State

Check logs:

```sh
docker compose logs worker
docker compose logs api
```

The worker healthcheck depends on database, Redis, and object storage readiness.

## Handoff Message

Use this when handing off to Backend 1:

```text
Backend 3 PR provides storage/export services and E2E scripts.

Please call storage/export services from Backend 1 Router/application code.
I did not add Router, DB tables, or migrations.

Required artifact fields:
- artifact_id
- bucket
- object_key
- filename
- content_type
- size_bytes
- sha256

Frontend 1 currently creates projects with reference_artifact_ids. Please wire POST /files to
FileArtifactService.store_file(), persist the returned metadata, and return artifact_id before
project creation.

Frontend 2 currently uses preview_asset_id + assetUrls. Please confirm whether Backend 1 will
hydrate those URLs in the workbench response or expose a separate artifact URL endpoint.

Required export contract decisions:
- POST /exports body
- Export orchestration run/table shape after EXPORT_READY
- export status query
- export task persistence model
- artifact lookup flow
- per-format retry/idempotency keys for PDF, PPTX, and ZIP
```
